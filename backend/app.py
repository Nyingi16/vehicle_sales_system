from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import stripe
import numpy as np
from sklearn.neighbors import NearestNeighbors
import pandas as pd
import json
from functools import wraps
from sqlalchemy import or_
import os
import secrets
import openai


app = Flask(__name__)
# Use environment variables for sensitive configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///vehicle_sales.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe configuration - use environment variables
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', '')

db = SQLAlchemy(app)
CORS(app)  # Configure CORS properly for production

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    role = db.Column(db.String(20), default='customer') # 'customer' or 'admin'
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # Store hashed passwords only
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    interactions = db.relationship('UserInteraction', backref='user', lazy=True)
    purchases = db.relationship('Purchase', backref='user', lazy=True)

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    mileage = db.Column(db.Integer)
    fuel_type = db.Column(db.String(20))
    transmission = db.Column(db.String(20))
    engine_size = db.Column(db.Numeric(3, 1))
    color = db.Column(db.String(30))
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))
    status = db.Column(db.String(20), default='available')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserInteraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    interaction_type = db.Column(db.String(50))  # view, search, favorite, purchase
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    vehicle = db.relationship('Vehicle')

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(50), default='pending')
    payment_method = db.Column(db.String(20))
    payment_intent_id = db.Column(db.String(200))
    admin_verified = db.Column(db.Boolean, default=False)
    verification_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    vehicle = db.relationship('Vehicle')

# AI-Powered Recommendation Engine
class VehicleRecommender:
    def __init__(self):
        self.model = NearestNeighbors(n_neighbors=5, metric='cosine')
        self.vehicles_df = None
        self.feature_columns = ['price', 'year', 'mileage', 'engine_size']
        
    def prepare_features(self, vehicles):
        """Prepare vehicle features for recommendation"""
        df = pd.DataFrame([{
            'id': v.id,
            'price': float(v.price),
            'year': v.year,
            'mileage': v.mileage if v.mileage else 0,
            'engine_size': float(v.engine_size) if v.engine_size else 0,
            'make': v.make,
            'model': v.model
        } for v in vehicles])
        
        # Normalize numerical features
        for col in self.feature_columns:
            if df[col].std() != 0:  # Avoid division by zero
                df[col] = (df[col] - df[col].mean()) / df[col].std()
            else:
                df[col] = 0
                
        return df
    
    def fit(self, vehicles):
        """Fit the recommendation model"""
        self.vehicles_df = self.prepare_features(vehicles)
        features = self.vehicles_df[self.feature_columns].values
        self.model.fit(features)
    
    def recommend(self, user_preferences, n_recommendations=5):
        """Get vehicle recommendations based on user preferences"""
        if self.vehicles_df is None or len(self.vehicles_df) == 0:
            return []
            
        # Convert user preferences to feature vector
        pref_vector = np.array([[
            float(user_preferences.get('price', 0)),
            int(user_preferences.get('year', 0)),
            int(user_preferences.get('mileage', 0)),
            float(user_preferences.get('engine_size', 0))
        ]])
        
        # Find similar vehicles
        n_neighbors = min(n_recommendations, len(self.vehicles_df))
        distances, indices = self.model.kneighbors(pref_vector, n_neighbors=n_neighbors)
        
        # Get recommended vehicles
        recommendations = []
        for idx in indices[0]:
            if idx < len(self.vehicles_df):
                vehicle_id = int(self.vehicles_df.iloc[idx]['id'])
                vehicle = Vehicle.query.get(vehicle_id)
                if vehicle and vehicle.status == 'available':
                    recommendations.append(vehicle)
        
        return recommendations

recommender = VehicleRecommender()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Look in JSON body (POST)
        data = request.get_json(silent=True) or {}
        # 2. Look in URL parameters (GET)
        # 3. Look in Flask Session
        user_id = data.get('user_id') or request.args.get('user_id') or session.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
            
        user = User.query.get(user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
            
        return f(*args, **kwargs)
    return decorated_function

# Endpoints
@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "message": "Vehicle Sales System API is running"
    })

# Customer Registration Endpoint
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    
    # Check if user already exists
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 400
    
    # In production, hash this password: password = generate_password_hash(data['password'])
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=data['password'],  # TODO: Hash this password
        phone=data.get('phone', ''),
        role='customer'  # Force role to customer for security
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({'message': 'Registration successful', 'user_id': new_user.id}), 201

# Login endpoint
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    login_id = data.get('username') 
    password = data.get('password')

    # Query: Find user where username matches OR email matches
    user = User.query.filter(
        or_(User.username == login_id, User.email == login_id)
    ).first()

    # In production, use check_password_hash(user.password, password)
    if user and user.password == password:  # TODO: Use proper password hashing
        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'email': user.email
            }
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

# ============= VEHICLE ENDPOINTS =============

# Get all vehicles with optional filters
@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    # Get query parameters for filtering
    make = request.args.get('make')
    model = request.args.get('model')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    min_year = request.args.get('min_year')
    max_year = request.args.get('max_year')
    fuel_type = request.args.get('fuel_type')
    transmission = request.args.get('transmission')
    status = request.args.get('status', 'available')
    
    # Build query
    query = Vehicle.query
    
    if make:
        query = query.filter(Vehicle.make.ilike(f'%{make}%'))
    if model:
        query = query.filter(Vehicle.model.ilike(f'%{model}%'))
    if min_price:
        query = query.filter(Vehicle.price >= float(min_price))
    if max_price:
        query = query.filter(Vehicle.price <= float(max_price))
    if min_year:
        query = query.filter(Vehicle.year >= int(min_year))
    if max_year:
        query = query.filter(Vehicle.year <= int(max_year))
    if fuel_type:
        query = query.filter(Vehicle.fuel_type == fuel_type)
    if transmission:
        query = query.filter(Vehicle.transmission == transmission)
    if status:
        query = query.filter(Vehicle.status == status)
    
    vehicles = query.all()
    
    result = [{
        'id': v.id,
        'make': v.make,
        'model': v.model,
        'year': v.year,
        'price': float(v.price),
        'mileage': v.mileage,
        'fuel_type': v.fuel_type,
        'transmission': v.transmission,
        'engine_size': float(v.engine_size) if v.engine_size else None,
        'color': v.color,
        'description': v.description,
        'image_url': v.image_url,
        'status': v.status,
        'created_at': v.created_at.isoformat() if v.created_at else None
    } for v in vehicles]
    
    return jsonify(result)

# Get single vehicle by ID
@app.route('/api/vehicles/<int:vehicle_id>', methods=['GET'])
def get_vehicle(vehicle_id):
    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    # Log view interaction if user_id provided
    user_id = request.args.get('user_id')
    if user_id:
        try:
            interaction = UserInteraction(
                user_id=int(user_id),
                vehicle_id=vehicle_id,
                interaction_type='view'
            )
            db.session.add(interaction)
            db.session.commit()
        except:
            pass  # Don't fail if logging fails
    
    result = {
        'id': vehicle.id,
        'make': vehicle.make,
        'model': vehicle.model,
        'year': vehicle.year,
        'price': float(vehicle.price),
        'mileage': vehicle.mileage,
        'fuel_type': vehicle.fuel_type,
        'transmission': vehicle.transmission,
        'engine_size': float(vehicle.engine_size) if vehicle.engine_size else None,
        'color': vehicle.color,
        'description': vehicle.description,
        'image_url': vehicle.image_url,
        'status': vehicle.status,
        'created_at': vehicle.created_at.isoformat() if vehicle.created_at else None
    }
    
    return jsonify(result)

# Update vehicle
@app.route('/api/vehicles/<int:vehicle_id>', methods=['PUT'])
@admin_required
def update_vehicle(vehicle_id):
    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    data = request.json
    
    try:
        # Update fields if provided
        if 'make' in data:
            vehicle.make = data['make']
        if 'model' in data:
            vehicle.model = data['model']
        if 'year' in data:
            vehicle.year = data['year']
        if 'price' in data:
            vehicle.price = data['price']
        if 'mileage' in data:
            vehicle.mileage = data['mileage']
        if 'fuel_type' in data:
            vehicle.fuel_type = data['fuel_type']
        if 'transmission' in data:
            vehicle.transmission = data['transmission']
        if 'engine_size' in data:
            vehicle.engine_size = data['engine_size']
        if 'color' in data:
            vehicle.color = data['color']
        if 'description' in data:
            vehicle.description = data['description']
        if 'image_url' in data:
            vehicle.image_url = data['image_url']
        if 'status' in data:
            vehicle.status = data['status']
        
        db.session.commit()
        return jsonify({'message': 'Vehicle updated successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Delete vehicle
@app.route('/api/vehicles/<int:vehicle_id>', methods=['DELETE'])
@admin_required
def delete_vehicle(vehicle_id):
    vehicle = Vehicle.query.get(vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    
    try:
        # Check if vehicle has any related purchases
        purchases = Purchase.query.filter_by(vehicle_id=vehicle_id).first()
        if purchases:
            return jsonify({'error': 'Cannot delete vehicle with purchase history'}), 400
        
        # Delete related interactions first
        UserInteraction.query.filter_by(vehicle_id=vehicle_id).delete()
        
        # Delete the vehicle
        db.session.delete(vehicle)
        db.session.commit()
        
        return jsonify({'message': 'Vehicle deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ============= USER INTERACTION ENDPOINTS =============

# Add favorite vehicle
@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    data = request.json
    user_id = data.get('user_id')
    vehicle_id = data.get('vehicle_id')
    
    if not user_id or not vehicle_id:
        return jsonify({'error': 'user_id and vehicle_id are required'}), 400
    
    # Check if already favorited
    existing = UserInteraction.query.filter_by(
        user_id=user_id,
        vehicle_id=vehicle_id,
        interaction_type='favorite'
    ).first()
    
    if existing:
        return jsonify({'message': 'Vehicle already in favorites'}), 200
    
    interaction = UserInteraction(
        user_id=user_id,
        vehicle_id=vehicle_id,
        interaction_type='favorite'
    )
    
    db.session.add(interaction)
    db.session.commit()
    
    return jsonify({'message': 'Added to favorites'}), 201

# Remove favorite vehicle
@app.route('/api/favorites', methods=['DELETE'])
def remove_favorite():
    data = request.json
    user_id = data.get('user_id')
    vehicle_id = data.get('vehicle_id')
    
    if not user_id or not vehicle_id:
        return jsonify({'error': 'user_id and vehicle_id are required'}), 400
    
    interaction = UserInteraction.query.filter_by(
        user_id=user_id,
        vehicle_id=vehicle_id,
        interaction_type='favorite'
    ).first()
    
    if interaction:
        db.session.delete(interaction)
        db.session.commit()
        return jsonify({'message': 'Removed from favorites'})
    
    return jsonify({'error': 'Favorite not found'}), 404

# Get user favorites
@app.route('/api/favorites/<int:user_id>', methods=['GET'])
def get_favorites(user_id):
    favorites = UserInteraction.query.filter_by(
        user_id=user_id,
        interaction_type='favorite'
    ).all()
    
    vehicles = []
    for fav in favorites:
        vehicle = Vehicle.query.get(fav.vehicle_id)
        if vehicle:
            vehicles.append({
                'id': vehicle.id,
                'make': vehicle.make,
                'model': vehicle.model,
                'year': vehicle.year,
                'price': float(vehicle.price),
                'image_url': vehicle.image_url,
                'status': vehicle.status
            })
    
    return jsonify(vehicles)

# ============= PURCHASE ENDPOINTS =============

# Get user purchases
@app.route('/api/purchases/user/<int:user_id>', methods=['GET'])
def get_user_purchases(user_id):
    purchases = Purchase.query.filter_by(user_id=user_id).all()
    
    result = [{
        'id': p.id,
        'vehicle_id': p.vehicle_id,
        'vehicle': {
            'make': p.vehicle.make,
            'model': p.vehicle.model,
            'year': p.vehicle.year,
            'image_url': p.vehicle.image_url
        } if p.vehicle else None,
        'amount': p.amount,
        'payment_status': p.payment_status,
        'admin_verified': p.admin_verified,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'verification_date': p.verification_date.isoformat() if p.verification_date else None
    } for p in purchases]
    
    return jsonify(result)

# Get all purchases (admin only)
@app.route('/api/admin/purchases', methods=['GET'])
@admin_required
def get_all_purchases():
    purchases = Purchase.query.all()
    
    result = [{
        'id': p.id,
        'user_id': p.user_id,
        'user': {
            'username': p.user.username,
            'email': p.user.email
        } if p.user else None,
        'vehicle_id': p.vehicle_id,
        'vehicle': {
            'make': p.vehicle.make,
            'model': p.vehicle.model,
            'year': p.vehicle.year
        } if p.vehicle else None,
        'amount': p.amount,
        'payment_status': p.payment_status,
        'admin_verified': p.admin_verified,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'verification_date': p.verification_date.isoformat() if p.verification_date else None
    } for p in purchases]
    
    return jsonify(result)

# ============= USER MANAGEMENT ENDPOINTS =============

# Get all users (admin only)
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    users = User.query.all()
    
    result = [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': u.role,
        'phone': u.phone,
        'created_at': u.created_at.isoformat() if u.created_at else None,
        'interaction_count': len(u.interactions),
        'purchase_count': len(u.purchases)
    } for u in users]
    
    return jsonify(result)

# Get single user
@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    result = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'phone': user.phone,
        'created_at': user.created_at.isoformat() if user.created_at else None
    }
    
    return jsonify(result)

# Update user
@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.json
    
    try:
        if 'username' in data:
            # Check if username is taken
            existing = User.query.filter(User.username == data['username'], User.id != user_id).first()
            if existing:
                return jsonify({'error': 'Username already taken'}), 400
            user.username = data['username']
        
        if 'email' in data:
            # Check if email is taken
            existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
            if existing:
                return jsonify({'error': 'Email already registered'}), 400
            user.email = data['email']
        
        if 'phone' in data:
            user.phone = data['phone']
        
        # Only admin can change role
        if 'role' in data:
            # Check if requester is admin
            requester_id = data.get('requester_id')
            requester = User.query.get(requester_id)
            if not requester or requester.role != 'admin':
                return jsonify({'error': 'Unauthorized to change role'}), 403
            user.role = data['role']
        
        db.session.commit()
        return jsonify({'message': 'User updated successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# Delete user (admin only)
@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    try:
        # Delete related records
        UserInteraction.query.filter_by(user_id=user_id).delete()
        Purchase.query.filter_by(user_id=user_id).delete()
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'message': 'User deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ============= VEHICLE RECOMMENDATION ENDPOINTS =============

# Get recommendations based on user preferences
@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    data = request.json
    user_id = data.get('user_id')
    preferences = data.get('preferences', {})
    
    # Get all available vehicles
    vehicles = Vehicle.query.filter_by(status='available').all()
    
    if not vehicles:
        return jsonify({
            'recommendations': [],
            'total': 0,
            'message': 'No vehicles available'
        })
    
    # Fit recommender with current vehicles
    recommender.fit(vehicles)
    
    # Get ALL recommendations (no limit - frontend handles pagination)
    recommendations = recommender.recommend(preferences, n_recommendations=len(vehicles))
    
    # Log user interaction for CRM (only log first few to avoid too many DB operations)
    if user_id and recommendations:
        for vehicle in recommendations[:3]:
            interaction = UserInteraction(
                user_id=user_id,
                vehicle_id=vehicle.id,
                interaction_type='recommendation'
            )
            db.session.add(interaction)
        db.session.commit()
    
    # Format response with all recommendations
    result = [{
        'id': v.id,
        'make': v.make,
        'model': v.model,
        'year': v.year,
        'price': float(v.price),
        'mileage': v.mileage,
        'fuel_type': v.fuel_type,
        'transmission': v.transmission,
        'engine_size': float(v.engine_size) if v.engine_size else None,
        'color': v.color,
        'image_url': v.image_url,
        'description': v.description[:200] + '...' if v.description and len(v.description) > 200 else v.description,
        'status': v.status
    } for v in recommendations]
    
    # Return all recommendations with metadata
    return jsonify({
        'status': 'success',
        'recommendations': result,
        'total': len(result),
        'message': f'Found {len(result)} recommendations'
    })

# Get paginated recommendations based on user preferences
@app.route('/api/recommendations/paginated', methods=['POST'])
def get_paginated_recommendations():
    data = request.json
    user_id = data.get('user_id')
    preferences = data.get('preferences', {})
    
    # Pagination parameters from request
    page = data.get('page', 1)
    per_page = data.get('per_page', 12)
    
    # Get all available vehicles
    vehicles = Vehicle.query.filter_by(status='available').all()
    
    if not vehicles:
        return jsonify({
            'status': 'success',
            'data': {
                'recommendations': [],
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_items': 0,
                    'total_pages': 0,
                    'has_next': False,
                    'has_previous': False
                }
            }
        })
    
    # Fit recommender with current vehicles
    recommender.fit(vehicles)
    
    # Get ALL recommendations (no limit)
    all_recommendations = recommender.recommend(preferences, n_recommendations=len(vehicles))
    
    # Log user interaction for CRM (only log first few)
    if user_id and all_recommendations:
        for vehicle in all_recommendations[:3]:
            interaction = UserInteraction(
                user_id=user_id,
                vehicle_id=vehicle.id,
                interaction_type='recommendation'
            )
            db.session.add(interaction)
        db.session.commit()
    
    # Calculate pagination
    total_items = len(all_recommendations)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    # Get paginated recommendations
    paginated_recommendations = all_recommendations[start_idx:end_idx]
    
    # Format response
    result = [{
        'id': v.id,
        'make': v.make,
        'model': v.model,
        'year': v.year,
        'price': float(v.price),
        'mileage': v.mileage,
        'fuel_type': v.fuel_type,
        'transmission': v.transmission,
        'engine_size': float(v.engine_size) if v.engine_size else None,
        'color': v.color,
        'image_url': v.image_url,
        'description': v.description[:200] + '...' if v.description and len(v.description) > 200 else v.description,
        'status': v.status
    } for v in paginated_recommendations]
    
    return jsonify({
        'status': 'success',
        'data': {
            'recommendations': result,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_items': total_items,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_previous': page > 1,
                'next_page': page + 1 if page < total_pages else None,
                'previous_page': page - 1 if page > 1 else None
            }
        }
    })

# Get recommendations for a specific user based on their history
@app.route('/api/recommendations/user/<int:user_id>', methods=['GET'])
def get_user_recommendations(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    
    # Get user's interaction history
    interactions = UserInteraction.query.filter_by(user_id=user_id).all()
    
    if not interactions:
        # If no history, return popular vehicles (all of them)
        popular_vehicles = Vehicle.query.filter_by(status='available').order_by(Vehicle.created_at.desc()).all()
        total_items = len(popular_vehicles)
        
        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_vehicles = popular_vehicles[start_idx:end_idx]
        
        result = [{
            'id': v.id,
            'make': v.make,
            'model': v.model,
            'year': v.year,
            'price': float(v.price),
            'image_url': v.image_url,
            'mileage': v.mileage,
            'fuel_type': v.fuel_type,
            'transmission': v.transmission
        } for v in paginated_vehicles]
        
        return jsonify({
            'status': 'success',
            'data': {
                'recommendations': result,
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_items': total_items,
                    'total_pages': (total_items + per_page - 1) // per_page,
                    'has_next': page < ((total_items + per_page - 1) // per_page),
                    'has_previous': page > 1
                }
            }
        })
    
    # Get vehicles user has interacted with
    vehicle_ids = list(set([i.vehicle_id for i in interactions]))
    vehicles = Vehicle.query.filter(Vehicle.id.in_(vehicle_ids)).all()
    
    if not vehicles:
        return jsonify({
            'status': 'success',
            'data': {
                'recommendations': [],
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_items': 0,
                    'total_pages': 0,
                    'has_next': False,
                    'has_previous': False
                }
            }
        })
    
    # Calculate average preferences from user's history
    avg_prefs = {
        'price': float(np.mean([float(v.price) for v in vehicles])),
        'year': int(np.mean([v.year for v in vehicles])),
        'mileage': int(np.mean([v.mileage for v in vehicles if v.mileage]) or 0),
        'engine_size': float(np.mean([float(v.engine_size) for v in vehicles if v.engine_size]) or 0)
    }
    
    # Get recommendations based on average preferences
    available_vehicles = Vehicle.query.filter_by(status='available').all()
    if available_vehicles:
        recommender.fit(available_vehicles)
        # Get ALL recommendations (no limit)
        all_recommendations = recommender.recommend(avg_prefs, n_recommendations=len(available_vehicles))
        
        # Filter out vehicles user has already interacted with
        all_recommendations = [v for v in all_recommendations if v.id not in vehicle_ids]
        
        total_items = len(all_recommendations)
        
        # Apply pagination
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_recommendations = all_recommendations[start_idx:end_idx]
        
        result = [{
            'id': v.id,
            'make': v.make,
            'model': v.model,
            'year': v.year,
            'price': float(v.price),
            'image_url': v.image_url,
            'mileage': v.mileage,
            'fuel_type': v.fuel_type,
            'transmission': v.transmission
        } for v in paginated_recommendations]
        
        return jsonify({
            'status': 'success',
            'data': {
                'recommendations': result,
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'total_items': total_items,
                    'total_pages': (total_items + per_page - 1) // per_page,
                    'has_next': page < ((total_items + per_page - 1) // per_page),
                    'has_previous': page > 1,
                    'next_page': page + 1 if page < ((total_items + per_page - 1) // per_page) else None,
                    'previous_page': page - 1 if page > 1 else None
                }
            }
        })
    
    return jsonify({
        'status': 'success',
        'data': {
            'recommendations': [],
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_items': 0,
                'total_pages': 0,
                'has_next': False,
                'has_previous': False
            }
        }
    })

# ============= PAYMENT PROCESSING ENDPOINTS =============

@app.route('/api/create-payment-intent', methods=['POST'])
def create_payment():
    data = request.json
    vehicle_id = data.get('vehicle_id')
    user_id = data.get('user_id')
    payment_method = data.get('payment_method') # Expecting 'stripe' or 'manual'

    # Fixed Legacy Warning: Using db.session.get instead of .query.get
    vehicle = db.session.get(Vehicle, vehicle_id)
    
    if not vehicle or vehicle.status != 'available':
        return jsonify({'error': 'Vehicle not available or already sold'}), 400

    try:
        # OPTION 1: MANUAL / CASH PAYMENT
        if payment_method == 'manual':
            purchase = Purchase(
                user_id=user_id,
                vehicle_id=vehicle_id,
                amount=float(vehicle.price),
                payment_status='PENDING_ADMIN_APPROVAL', # New status for manual flow
                payment_method='manual'
            )
            db.session.add(purchase)
            db.session.commit()
            
            return jsonify({
                'message': 'Purchase request submitted. Please proceed with payment as instructed.',
                'purchase_id': purchase.id,
                'requires_approval': True
            }), 201

        # OPTION 2: STRIPE PAYMENT
        elif payment_method == 'stripe':
            # Create Stripe payment intent
            intent = stripe.PaymentIntent.create(
                amount=int(float(vehicle.price) * 100),
                currency='usd',
                metadata={
                    'vehicle_id': vehicle_id,
                    'user_id': user_id
                }
            )
            
            purchase = Purchase(
                user_id=user_id,
                vehicle_id=vehicle_id,
                amount=float(vehicle.price),
                payment_intent_id=intent.id,
                payment_status='AWAITING_STRIPE_PAYMENT',
                payment_method='stripe'
            )
            db.session.add(purchase)
            db.session.commit()
            
            return jsonify({
                'clientSecret': intent.client_secret,
                'purchase_id': purchase.id,
                'requires_approval': False
            })

        else:
            return jsonify({'error': 'Invalid payment method selected'}), 400
        
    except Exception as e:
        db.session.rollback() # Good practice to rollback on failure
        return jsonify({'error': str(e)}), 500

@app.route('/api/payment-confirmation', methods=['POST'])
def confirm_payment():
    data = request.json
    payment_intent_id = data.get('payment_intent_id')
    
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status == 'succeeded':
            # Use filter_by to find the purchase linked to this Stripe ID
            purchase = Purchase.query.filter_by(payment_intent_id=payment_intent_id).first()
            if purchase:
                purchase.status = 'completed' # Sync with your model field name
                
                vehicle = db.session.get(Vehicle, purchase.vehicle_id)
                if vehicle:
                    vehicle.status = 'sold'
                
                # Log interaction
                interaction = UserInteraction(
                    user_id=purchase.user_id,
                    vehicle_id=purchase.vehicle_id,
                    interaction_type='purchase'
                )
                db.session.add(interaction)
                db.session.commit()
                
            return jsonify({'status': 'success'})
        return jsonify({'status': 'pending'})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============= ADMIN ENDPOINTS =============

@app.route('/api/admin/add-vehicle', methods=['POST'])
@admin_required
def add_vehicle():
    data = request.json
    try:
        new_vehicle = Vehicle(
            make=data['make'],
            model=data['model'],
            year=data['year'],
            price=data['price'],
            mileage=data.get('mileage', 0),
            fuel_type=data.get('fuel_type'),
            transmission=data.get('transmission'),
            engine_size=data.get('engine_size'),
            color=data.get('color'),
            description=data.get('description'),
            image_url=data.get('image_url'),
            status='available'
        )
        db.session.add(new_vehicle)
        db.session.commit()
        return jsonify({'message': 'Vehicle added successfully', 'id': new_vehicle.id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/admin/add-admin', methods=['POST'])
@admin_required
def add_admin():
    data = request.json
    # Check if the username/email already exists
    if User.query.filter(or_(User.username == data['username'], User.email == data['email'])).first():
        return jsonify({'error': 'User already exists'}), 400
    
    new_admin = User(
        username=data['username'],
        email=data['email'],
        password=data['password'],  # TODO: Hash this password
        role='admin',
        phone=data.get('phone', '')
    )
    db.session.add(new_admin)
    db.session.commit()
    return jsonify({'message': f'Admin {data["username"]} created successfully'}), 201

# Route to confirm a cash payment and mark the vehicle as sold
# Route to confirm a cash payment and mark the vehicle as sold
@app.route('/api/admin/verify-purchase/<int:purchase_id>', methods=['POST'])
@admin_required
def verify_purchase(purchase_id):
    purchase = Purchase.query.get(purchase_id)
    if not purchase:
        return jsonify({'error': 'Purchase not found'}), 404
        
    # Update Purchase Status
    purchase.payment_status = 'completed'
    purchase.admin_verified = True
    purchase.verification_date = datetime.utcnow()
    
    # Automatically mark the Vehicle as Sold
    vehicle = Vehicle.query.get(purchase.vehicle_id)
    if vehicle:
        vehicle.status = 'sold'
        
    db.session.commit()
    
    # Return success with purchase data
    return jsonify({
        'message': 'Payment verified and vehicle marked as sold',
        'purchase': {
            'id': purchase.id,
            'payment_status': purchase.payment_status,
            'admin_verified': purchase.admin_verified
        }
    })
# ============= CRM ENDPOINTS =============

@app.route('/api/crm/user-insights/<int:user_id>', methods=['GET'])
@admin_required
def get_user_insights(user_id):
    """Generate insights about user behavior and preferences"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Get user interactions
    interactions = UserInteraction.query.filter_by(user_id=user_id).all()
    
    # Analyze viewing patterns
    viewed_vehicles = [i.vehicle for i in interactions if i.interaction_type == 'view' and i.vehicle]
    
    # Calculate preference scores
    preferences = {
        'most_viewed_make': _get_most_common([v.make for v in viewed_vehicles]),
        'price_range': {
            'min': float(min([float(v.price) for v in viewed_vehicles])) if viewed_vehicles else 0,
            'max': float(max([float(v.price) for v in viewed_vehicles])) if viewed_vehicles else 0
        },
        'preferred_fuel_types': list(set([v.fuel_type for v in viewed_vehicles if v.fuel_type])),
        'engagement_score': len(interactions),
        'purchase_readiness': _calculate_purchase_readiness(user)
    }
    
    # Generate personalized recommendations
    recommended_vehicles = _get_personalized_recommendations(user_id)
    
    return jsonify({
        'user_id': user_id,
        'preferences': preferences,
        'recommended_vehicles': recommended_vehicles,
        'interaction_summary': {
            'total_interactions': len(interactions),
            'views': len([i for i in interactions if i.interaction_type == 'view']),
            'favorites': len([i for i in interactions if i.interaction_type == 'favorite']),
            'recommendations': len([i for i in interactions if i.interaction_type == 'recommendation']),
            'purchases': len([i for i in interactions if i.interaction_type == 'purchase'])
        }
    })

# Helper functions for CRM
def _get_most_common(items):
    """Helper function to get most common item"""
    if not items:
        return None
    return max(set(items), key=items.count)

def _calculate_purchase_readiness(user):
    """Calculate user's likelihood to purchase"""
    recent_interactions = UserInteraction.query.filter_by(
        user_id=user.id
    ).filter(
        UserInteraction.timestamp > datetime.utcnow() - timedelta(days=30)
    ).all()
    
    # Simple scoring algorithm
    score = len(recent_interactions) * 10
    purchases = Purchase.query.filter_by(user_id=user.id).count()
    if purchases > 0:
        score += 50
    
    return min(score, 100)

def _get_personalized_recommendations(user_id):
    """Get personalized vehicle recommendations based on user history"""
    user_interactions = UserInteraction.query.filter_by(user_id=user_id).all()
    
    if not user_interactions:
        return []
    
    # Get vehicles user has interacted with
    vehicle_ids = [i.vehicle_id for i in user_interactions]
    vehicles = Vehicle.query.filter(Vehicle.id.in_(vehicle_ids)).all()
    
    # Use recommender to find similar vehicles
    if vehicles:
        # Get all available vehicles
        available_vehicles = Vehicle.query.filter_by(status='available').all()
        if available_vehicles:
            recommender.fit(available_vehicles)
            # Extract average preferences
            avg_prefs = {
                'price': float(np.mean([float(v.price) for v in vehicles])),
                'year': int(np.mean([v.year for v in vehicles])),
                'mileage': int(np.mean([v.mileage for v in vehicles if v.mileage])),
                'engine_size': float(np.mean([float(v.engine_size) for v in vehicles if v.engine_size]))
            }
            recommendations = recommender.recommend(avg_prefs, n_recommendations=3)
            return [{'id': v.id, 'make': v.make, 'model': v.model, 'year': v.year, 'price': float(v.price)} for v in recommendations]
    
    return []

# ============= CRM DASHBOARD ENDPOINTS =============

@app.route('/api/crm/dashboard', methods=['GET'])
@admin_required
def get_crm_dashboard():
    """Get CRM dashboard statistics"""
    # Total users
    total_users = User.query.count()
    
    # Total vehicles
    total_vehicles = Vehicle.query.count()
    available_vehicles = Vehicle.query.filter_by(status='available').count()
    sold_vehicles = Vehicle.query.filter_by(status='sold').count()
    
    # Total purchases
    total_purchases = Purchase.query.count()
    completed_purchases = Purchase.query.filter_by(payment_status='completed').count()
    pending_purchases = Purchase.query.filter_by(payment_status='pending').count()
    verified_purchases = Purchase.query.filter_by(admin_verified=True).count()
    
    # Total revenue
    total_revenue = db.session.query(db.func.sum(Purchase.amount)).filter_by(payment_status='completed').scalar() or 0
    
    # Recent interactions
    recent_interactions = UserInteraction.query.order_by(UserInteraction.timestamp.desc()).limit(20).all()
    
    # Popular vehicles (most viewed)
    popular_vehicles = db.session.query(
        Vehicle.id, Vehicle.make, Vehicle.model, 
        db.func.count(UserInteraction.id).label('view_count')
    ).join(UserInteraction, UserInteraction.vehicle_id == Vehicle.id)\
     .filter(UserInteraction.interaction_type == 'view')\
     .group_by(Vehicle.id)\
     .order_by(db.func.count(UserInteraction.id).desc())\
     .limit(10).all()
    
    return jsonify({
        'statistics': {
            'total_users': total_users,
            'total_vehicles': total_vehicles,
            'available_vehicles': available_vehicles,
            'sold_vehicles': sold_vehicles,
            'total_purchases': total_purchases,
            'completed_purchases': completed_purchases,
            'pending_purchases': pending_purchases,
            'verified_purchases': verified_purchases,
            'total_revenue': float(total_revenue)
        },
        'popular_vehicles': [{
            'id': v[0],
            'make': v[1],
            'model': v[2],
            'view_count': v[3]
        } for v in popular_vehicles],
        'recent_activity': [{
            'user_id': i.user_id,
            'username': i.user.username if i.user else None,
            'vehicle_id': i.vehicle_id,
            'vehicle': f"{i.vehicle.make} {i.vehicle.model}" if i.vehicle else None,
            'interaction_type': i.interaction_type,
            'timestamp': i.timestamp.isoformat() if i.timestamp else None
        } for i in recent_interactions]
    })

# ============= SEARCH ENDPOINTS =============

@app.route('/api/search', methods=['GET'])
def search_vehicles():
    """Advanced search endpoint"""
    query = request.args.get('q', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_year = request.args.get('min_year', type=int)
    max_year = request.args.get('max_year', type=int)
    fuel_type = request.args.get('fuel_type')
    transmission = request.args.get('transmission')
    sort_by = request.args.get('sort_by', 'created_at')  # price, year, mileage, created_at
    sort_order = request.args.get('sort_order', 'desc')  # asc or desc
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    # Build base query
    vehicle_query = Vehicle.query.filter_by(status='available')
    
    # Apply text search if provided
    if query:
        search_filter = or_(
            Vehicle.make.ilike(f'%{query}%'),
            Vehicle.model.ilike(f'%{query}%'),
            Vehicle.description.ilike(f'%{query}%')
        )
        vehicle_query = vehicle_query.filter(search_filter)
    
    # Apply filters
    if min_price is not None:
        vehicle_query = vehicle_query.filter(Vehicle.price >= min_price)
    if max_price is not None:
        vehicle_query = vehicle_query.filter(Vehicle.price <= max_price)
    if min_year is not None:
        vehicle_query = vehicle_query.filter(Vehicle.year >= min_year)
    if max_year is not None:
        vehicle_query = vehicle_query.filter(Vehicle.year <= max_year)
    if fuel_type:
        vehicle_query = vehicle_query.filter(Vehicle.fuel_type == fuel_type)
    if transmission:
        vehicle_query = vehicle_query.filter(Vehicle.transmission == transmission)
    
    # Apply sorting
    if sort_by in ['price', 'year', 'mileage', 'created_at']:
        sort_column = getattr(Vehicle, sort_by)
        if sort_order == 'desc':
            vehicle_query = vehicle_query.order_by(sort_column.desc())
        else:
            vehicle_query = vehicle_query.order_by(sort_column.asc())
    
    # Get total count before pagination
    total_count = vehicle_query.count()
    
    # Apply pagination
    vehicles = vehicle_query.limit(limit).offset(offset).all()
    
    # Format results
    results = [{
        'id': v.id,
        'make': v.make,
        'model': v.model,
        'year': v.year,
        'price': float(v.price),
        'mileage': v.mileage,
        'fuel_type': v.fuel_type,
        'transmission': v.transmission,
        'engine_size': float(v.engine_size) if v.engine_size else None,
        'color': v.color,
        'image_url': v.image_url,
        'created_at': v.created_at.isoformat() if v.created_at else None
    } for v in vehicles]
    
    return jsonify({
        'total': total_count,
        'offset': offset,
        'limit': limit,
        'results': results
    })

# ============= AUTH ENDPOINTS =============

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out from server'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    user_id = request.args.get('user_id') or session.get('user_id')
    if not user_id:
        return jsonify({'authenticated': False}), 200
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'authenticated': False}), 200
    
    return jsonify({
        'authenticated': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'email': user.email
        }
    })

# ============= STATISTICS ENDPOINTS =============

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get public statistics about the platform"""
    
    # Total available vehicles
    total_vehicles = Vehicle.query.filter_by(status='available').count()
    
    # Get makes and counts
    make_counts = db.session.query(
        Vehicle.make, db.func.count(Vehicle.id)
    ).filter_by(status='available').group_by(Vehicle.make).all()
    
    # Price range
    min_price = db.session.query(db.func.min(Vehicle.price)).filter_by(status='available').scalar() or 0
    max_price = db.session.query(db.func.max(Vehicle.price)).filter_by(status='available').scalar() or 0
    avg_price = db.session.query(db.func.avg(Vehicle.price)).filter_by(status='available').scalar() or 0
    
    # Fuel type distribution
    fuel_counts = db.session.query(
        Vehicle.fuel_type, db.func.count(Vehicle.id)
    ).filter_by(status='available').group_by(Vehicle.fuel_type).all()
    
    return jsonify({
        'total_vehicles': total_vehicles,
        'makes': [{'make': m[0], 'count': m[1]} for m in make_counts],
        'price_range': {
            'min': float(min_price),
            'max': float(max_price),
            'average': float(avg_price)
        },
        'fuel_types': [{'type': f[0], 'count': f[1]} for f in fuel_counts if f[0]]
    })

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    
    if user:
        # Generate a unique secure token
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        db.session.commit()
        
        # In production, send this via email. For now, we return it for testing.
        return jsonify({
            'message': 'Reset token generated.',
            'debug_token': token  # Remove this line in production!
        }), 200
    
    return jsonify({'error': 'Email not found'}), 404

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    token = data.get('token')
    new_password = data.get('password')
    
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 400
    
    user.password = new_password # Update to new password
    user.reset_token = None      # Clear token so it can't be reused
    db.session.commit()
    
    return jsonify({'message': 'Password updated successfully'}), 200

# In app.py
@app.route('/api/admin/add-aux-admin', methods=['POST'])
def add_aux_admin():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password') # In production, use werkzeug.security.generate_password_hash
    
    # Validation
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    # Create new Admin user
    new_admin = User(
        username=username,
        email=email,
        password=password,
        role='admin' # Explicitly set role to admin
    )

    try:
        db.session.add(new_admin)
        db.session.commit()
        return jsonify({'message': f'Admin {username} registered successfully!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/orders/<int:user_id>', methods=['GET'])
def get_user_orders(user_id):
    purchases = Purchase.query.filter_by(user_id=user_id).order_by(Purchase.created_at.desc()).all()
    
    output = []
    for p in purchases:
        # Fetch vehicle details to show the name in the order list
        vehicle = Vehicle.query.get(p.vehicle_id)
        output.append({
            'id': p.id,
            'vehicle': f"{vehicle.year} {vehicle.make} {vehicle.model}" if vehicle else "Unknown Vehicle",
            'amount': p.amount,
            'status': p.payment_status,
            'method': p.payment_method,
            'date': p.created_at.strftime("%b %d, %Y")
        })
    return jsonify(output)
    
client = openai.OpenAI(api_key="YOUR_OPENAI_API_KEY_HERE")

@app.route('/api/chatbot', methods=['POST'])
def ai_chatbot():
    data = request.json
    user_query = data.get('message')
    
    # 1. Fetch real-time inventory for the AI's "Knowledge"
    available_cars = Vehicle.query.filter_by(status='available').all()
    inventory_list = [f"{v.year} {v.make} {v.model} (${v.price})" for v in available_cars]
    context = ", ".join(inventory_list)

    try:
        # 2. Call OpenAI with a System Prompt
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": f"You are DriveSelect AI, a helpful car sales assistant. Current inventory: {context}. If a user asks for a car we don't have, suggest the closest match. Always be professional and encourage a test drive."
                },
                {"role": "user", "content": user_query}
            ],
            max_tokens=200
        )
        
        reply = response.choices[0].message.content
        return jsonify({'response': reply})
    
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return jsonify({'response': "I'm having trouble connecting to my brain. Try again in a moment!"}), 500
# Remove debug endpoint in production
# @app.route('/debug/users')  # Comment out in production

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database initialized.")

    port = int(os.environ.get('PORT', 5001))
    
    # Logic to print the local IP for easy phone testing
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"--- SERVER LIVE ---")
    print(f"Local Access: http://localhost:{port}")
    print(f"Phone Access: http://{local_ip}:{port}")
    print(f"-------------------")
    
    app.run(
        debug=os.environ.get('FLASK_ENV') == 'development', 
        host='0.0.0.0', 
        port=port
    )