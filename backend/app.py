from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
import numpy as np
from sklearn.neighbors import NearestNeighbors
import pandas as pd
import json
from functools import wraps
from sqlalchemy import or_
import os
import secrets
import openai
import base64
import requests
import re
from difflib import get_close_matches
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import string

# Download NLTK data (run once)
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')
    nltk.download('averaged_perceptron_tagger')

app = Flask(__name__)
# Use environment variables for sensitive configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///vehicle_sales.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# M-Pesa Daraja API Credentials (Use your Sandbox credentials)
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', 'your_consumer_key')
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', 'your_consumer_secret')
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '174379')
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919')
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', 'https://your-public-url.com/api/payments/callback')

db = SQLAlchemy(app)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "allow_headers": ["Content-Type", "Authorization", "ngrok-skip-browser-warning"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    }
})

# ============= DATABASE MODELS =============

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    role = db.Column(db.String(20), default='customer')
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    interactions = db.relationship('UserInteraction', backref='user', lazy=True)

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
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
    interaction_type = db.Column(db.String(50)) 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    vehicle = db.relationship('Vehicle')

class Purchase(db.Model):
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_id = db.Column(db.Integer, db.ForeignKey('vehicle.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(50), default='pending')
    payment_method = db.Column(db.String(20))
    mpesa_checkout_request_id = db.Column(db.String(200), nullable=True)
    mpesa_merchant_request_id = db.Column(db.String(200), nullable=True)
    mpesa_result_code = db.Column(db.String(10), nullable=True)
    mpesa_result_desc = db.Column(db.String(500), nullable=True)
    admin_verified = db.Column(db.Boolean, default=False)
    verification_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('purchase_history', lazy=True))
    vehicle = db.relationship('Vehicle', backref=db.backref('sale_record', lazy=True))

# ============= AI-POWERED RECOMMENDATION ENGINE =============

class VehicleRecommender:
    def __init__(self):
        self.model = NearestNeighbors(n_neighbors=5, metric='cosine')
        self.vehicles_df = None
        self.feature_columns = ['price', 'year', 'mileage', 'engine_size']
        
    def prepare_features(self, vehicles):
        df = pd.DataFrame([{
            'id': v.id,
            'price': float(v.price),
            'year': v.year,
            'mileage': v.mileage if v.mileage else 0,
            'engine_size': float(v.engine_size) if v.engine_size else 0,
            'make': v.make,
            'model': v.model
        } for v in vehicles])
        
        for col in self.feature_columns:
            if df[col].std() != 0:
                df[col] = (df[col] - df[col].mean()) / df[col].std()
            else:
                df[col] = 0
        return df
    
    def fit(self, vehicles):
        self.vehicles_df = self.prepare_features(vehicles)
        features = self.vehicles_df[self.feature_columns].values
        self.model.fit(features)
    
    def recommend(self, user_preferences, n_recommendations=5):
        if self.vehicles_df is None or len(self.vehicles_df) == 0:
            return []
        pref_vector = np.array([[
            float(user_preferences.get('price', 0)),
            int(user_preferences.get('year', 0)),
            int(user_preferences.get('mileage', 0)),
            float(user_preferences.get('engine_size', 0))
        ]])
        n_neighbors = min(n_recommendations, len(self.vehicles_df))
        distances, indices = self.model.kneighbors(pref_vector, n_neighbors=n_neighbors)
        recommendations = []
        for idx in indices[0]:
            if idx < len(self.vehicles_df):
                vehicle_id = int(self.vehicles_df.iloc[idx]['id'])
                vehicle = db.session.get(Vehicle, vehicle_id)
                if vehicle and vehicle.status == 'available':
                    recommendations.append(vehicle)
        return recommendations

recommender = VehicleRecommender()

# ============= HELPER FUNCTIONS =============

def get_mpesa_access_token():
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET), timeout=30)
        response.raise_for_status()
        return response.json().get('access_token')
    except requests.exceptions.RequestException as e:
        print(f"Error getting M-Pesa token: {e}")
        return None

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        user_id = data.get('user_id') or request.args.get('user_id') or session.get('user_id')
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        user = db.session.get(User, user_id)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Unauthorized. Admin access required.'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ============= NLP PROCESSING CLASS =============

class NLPProcessor:
    def __init__(self):
        self.lemmatizer = WordNetLemmatizer()
        self.stop_words = set(stopwords.words('english'))
        
        self.synonyms = {
            'price': ['cost', 'amount', 'rate', 'value', 'ksh', 'kes', 'shillings'],
            'mileage': ['kilometers', 'km', 'distance', 'driven', 'odometer'],
            'year': ['model year', 'manufacturing year', 'registration year'],
            'fuel_type': ['fuel', 'gas', 'petrol', 'diesel', 'electric', 'hybrid'],
            'transmission': ['gear', 'gearbox', 'auto', 'manual', 'cvt'],
            'make': ['brand', 'manufacturer', 'company'],
            'available': ['in stock', 'present', 'existing', 'on sale'],
            'warranty': ['guarantee', 'cover', 'protection'],
            'delivery': ['shipping', 'transport', 'send'],
            'payment': ['pay', 'mpesa', 'cash', 'finance', 'loan']
        }
        
        self.question_patterns = {
            'availability': ['do you have', 'is there', 'any', 'available', 'in stock'],
            'price_inquiry': ['how much', 'price', 'cost', 'expensive', 'cheap', 'what is the price'],
            'comparison': ['compare', 'versus', 'vs', 'difference', 'better than'],
            'specification': ['specs', 'specifications', 'features', 'details'],
            'process': ['how to', 'steps', 'procedure', 'way to', 'process'],
            'time': ['how long', 'when', 'timeline', 'duration', 'days', 'weeks']
        }
        
        self.number_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
            'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'hundred': 100,
            'thousand': 1000, 'million': 1000000
        }
    
    def preprocess_text(self, text):
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        tokens = word_tokenize(text)
        tokens = [self.lemmatizer.lemmatize(token) for token in tokens if token not in self.stop_words]
        return tokens
    
    def extract_numeric_value(self, text):
        numbers = []
        digit_matches = re.findall(r'\b\d+(?:,\d+)*(?:\.\d+)?\b', text)
        for match in digit_matches:
            numbers.append(float(match.replace(',', '')))
        
        words = text.lower().split()
        for i, word in enumerate(words):
            if word in self.number_words:
                if i + 1 < len(words) and words[i + 1] in ['thousand', 'million', 'hundred']:
                    multiplier = self.number_words[words[i + 1]]
                    numbers.append(self.number_words[word] * multiplier)
                else:
                    numbers.append(self.number_words[word])
        return numbers
    
    def extract_price_range(self, text):
        price_range = {'min': None, 'max': None}
        
        under_match = re.search(r'under\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?', text, re.IGNORECASE)
        if under_match:
            value = self._parse_price_value(under_match.group(1), text)
            price_range['max'] = value
        
        below_match = re.search(r'below\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?', text, re.IGNORECASE)
        if below_match:
            value = self._parse_price_value(below_match.group(1), text)
            price_range['max'] = value
        
        above_match = re.search(r'above\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?', text, re.IGNORECASE)
        if above_match:
            value = self._parse_price_value(above_match.group(1), text)
            price_range['min'] = value
        
        between_match = re.search(r'between\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?\s+and\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?', text, re.IGNORECASE)
        if between_match:
            price_range['min'] = self._parse_price_value(between_match.group(1), text)
            price_range['max'] = self._parse_price_value(between_match.group(2), text)
        
        from_to_match = re.search(r'from\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?\s+to\s+(\d+(?:,\d+)?)\s*(?:million|m|k|thousand)?', text, re.IGNORECASE)
        if from_to_match:
            price_range['min'] = self._parse_price_value(from_to_match.group(1), text)
            price_range['max'] = self._parse_price_value(from_to_match.group(2), text)
        
        return price_range
    
    def _parse_price_value(self, value_str, full_text):
        value = float(value_str.replace(',', ''))
        if 'million' in full_text.lower():
            value *= 1000000
        elif 'thousand' in full_text.lower():
            value *= 1000
        elif 'k' in full_text.lower():
            value *= 1000
        return value
    
    def extract_make_from_text(self, text):
        makes = ['toyota', 'honda', 'nissan', 'subaru', 'mitsubishi', 'mercedes', 
                 'bmw', 'audi', 'volkswagen', 'ford', 'hyundai', 'mazda', 'suzuki', 
                 'isuzu', 'mazda', 'peugeot', 'renault', 'kia', 'hyundai']
        text_lower = text.lower()
        for make in makes:
            if make in text_lower:
                return make
        return None
    
    def extract_model_from_text(self, text):
        models = ['fortuner', 'cr-v', 'x-trail', 'forester', 'c-class', 'x3', 
                  'vitz', 'fit', 'swift', 'passo', 'note', 'demio', 'axela', 
                  'premacy', 'camry', 'corolla', 'civic', 'accord']
        text_lower = text.lower()
        for model in models:
            if model in text_lower:
                return model
        return None
    
    def detect_intent(self, text):
        text_lower = text.lower()
        for intent, patterns in self.question_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return intent
        if any(word in text_lower for word in self.synonyms['price']):
            return 'price_inquiry'
        if any(word in text_lower for word in self.synonyms['available']):
            return 'availability'
        if any(word in text_lower for word in self.synonyms['payment']):
            return 'payment'
        return 'general'
    
    def extract_year(self, text):
        year_match = re.search(r'\b(20\d{2})\b', text)
        if year_match:
            return int(year_match.group(1))
        model_year_match = re.search(r'(?:model|version|year)\s+(?:of\s+)?(20\d{2})', text, re.IGNORECASE)
        if model_year_match:
            return int(model_year_match.group(1))
        return None
    
    def extract_mileage(self, text):
        mileage_match = re.search(r'(\d+(?:,\d+)?)\s*(?:miles|km|kilometers|mileage)', text, re.IGNORECASE)
        if mileage_match:
            return int(mileage_match.group(1).replace(',', ''))
        return None
    
    def extract_fuel_type(self, text):
        text_lower = text.lower()
        fuel_types = {
            'petrol': ['petrol', 'gasoline', 'gas'],
            'diesel': ['diesel'],
            'electric': ['electric', 'ev', 'electric vehicle'],
            'hybrid': ['hybrid', 'petrol-electric']
        }
        for fuel, keywords in fuel_types.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return fuel.capitalize()
        return None
    
    def extract_transmission(self, text):
        text_lower = text.lower()
        if 'automatic' in text_lower or 'auto' in text_lower:
            return 'Automatic'
        elif 'manual' in text_lower:
            return 'Manual'
        elif 'cvt' in text_lower:
            return 'CVT'
        return None
    
    def analyze_query(self, query):
        analysis = {
            'original_query': query,
            'tokens': self.preprocess_text(query),
            'intent': self.detect_intent(query),
            'entities': {},
            'price_range': None,
            'numerical_values': self.extract_numeric_value(query)
        }
        
        make = self.extract_make_from_text(query)
        if make:
            analysis['entities']['make'] = make
        
        model = self.extract_model_from_text(query)
        if model:
            analysis['entities']['model'] = model
        
        year = self.extract_year(query)
        if year:
            analysis['entities']['year'] = year
        
        mileage = self.extract_mileage(query)
        if mileage:
            analysis['entities']['mileage'] = mileage
        
        fuel_type = self.extract_fuel_type(query)
        if fuel_type:
            analysis['entities']['fuel_type'] = fuel_type
        
        transmission = self.extract_transmission(query)
        if transmission:
            analysis['entities']['transmission'] = transmission
        
        price_range = self.extract_price_range(query)
        if price_range['min'] or price_range['max']:
            analysis['price_range'] = price_range
        
        return analysis
    
    def generate_suggested_filters(self, analysis):
        suggestions = []
        if analysis['price_range']:
            if analysis['price_range']['max']:
                suggestions.append(f"under KSh {analysis['price_range']['max']:,.0f}")
            if analysis['price_range']['min']:
                suggestions.append(f"above KSh {analysis['price_range']['min']:,.0f}")
        if 'make' in analysis['entities']:
            suggestions.append(f"make: {analysis['entities']['make'].title()}")
        if 'model' in analysis['entities']:
            suggestions.append(f"model: {analysis['entities']['model'].title()}")
        if 'year' in analysis['entities']:
            suggestions.append(f"year: {analysis['entities']['year']}")
        if 'fuel_type' in analysis['entities']:
            suggestions.append(f"fuel: {analysis['entities']['fuel_type']}")
        if 'transmission' in analysis['entities']:
            suggestions.append(f"transmission: {analysis['entities']['transmission']}")
        return suggestions

# Initialize NLP Processor
nlp_processor = NLPProcessor()

# ============= INTELLIGENT CHATBOT WITH RAG AND NLP =============

# Initialize OpenAI client
openai.api_key = os.environ.get('OPENAI_API_KEY')
client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))

# Comprehensive Knowledge Base
PRODUCT_KNOWLEDGE = {
    'vehicle_types': {
        'suv': "SUVs offer higher ground clearance, spacious interiors, and off-road capability. Popular models include Toyota Fortuner, Honda CR-V, Subaru Forester.",
        'sedan': "Sedans offer comfortable seating for 5, good fuel economy, and smooth handling. Popular models include Mercedes C-Class, BMW 3 Series.",
        'hatchback': "Hatchbacks are compact, fuel-efficient, and perfect for city driving. Popular models include Toyota Vitz, Honda Fit, Suzuki Swift."
    },
    'maintenance': {
        'service_interval': "We recommend servicing every 5,000 km or 6 months, whichever comes first.",
        'warranty_coverage': "30-day warranty covers major mechanical components including engine, transmission, and drivetrain."
    },
    'purchase_process': {
        'steps': "1. Browse inventory → 2. Select vehicle → 3. Choose payment (M-Pesa/Cash) → 4. Make payment → 5. Receive verification → 6. Collect vehicle",
        'timeline': "Cash purchases: Same day collection. M-Pesa: 24-48 hours for verification."
    },
    'delivery_information': {
        'nairobi': "Free delivery within Nairobi CBD. Outskirts: KSh 5,000-10,000",
        'other_cities': "Mombasa: KSh 25,000, Kisumu: KSh 20,000, Nakuru: KSh 15,000, Eldoret: KSh 18,000"
    },
    'payment_methods': {
        'mpesa': "Pay via M-Pesa Paybill 174379. Your unique account number is generated during checkout.",
        'cash': "Cash payments accepted at our showroom in Nairobi.",
        'financing': "We partner with KCB, Equity, and Co-op Bank for vehicle financing. Minimum deposit 20%."
    }
}

# FAQ Database
FAQ_DATABASE = {
    'warranty': "All our vehicles come with a 30-day mechanical warranty covering engine, transmission, and drivetrain. Extended warranty up to 1 year available for purchase.",
    'financing': "We offer financing through KCB, Equity, and Co-op Bank. Terms: 12-48 months, 12-15% interest. Minimum deposit: 20%. Requires KRA PIN and 3 months' bank statements.",
    'delivery': "Free delivery in Nairobi. Other cities: Mombasa (KSh 25,000), Kisumu (KSh 20,000), Nakuru (KSh 15,000). Delivery takes 2-5 business days.",
    'test drive': "Test drives available at our Nairobi showroom. Schedule by calling 0700-000-000 or clicking 'Request Test Drive' on any vehicle page. Monday-Saturday, 8 AM-6 PM.",
    'documents': "Required: National ID/Passport, KRA PIN certificate, proof of residence (utility bill), 3 months' bank statements (for financing).",
    'mpesa': "M-Pesa Paybill: 174379. Your unique account number appears during checkout. Enter exact amount and use transaction code for verification.",
    'return policy': "7-day return policy for vehicles with major mechanical issues. Full refund if issue cannot be resolved. Terms apply.",
    'insurance': "Partner insurers: Jubilee, APA, GA Insurance. Comprehensive insurance rates from 3-5% of vehicle value annually.",
    'trade in': "Yes! Free vehicle valuation. Trade-in value deducted from purchase price. Bring your car for assessment.",
    'opening hours': "Monday-Saturday: 8 AM - 6 PM. Sunday: Closed. Public holidays: 9 AM - 3 PM.",
    'contact': "Phone: 0700-000-000 | Email: sales@driveselect.co.ke | Location: Nairobi, Kenya",
    'price negotiation': "Prices are fixed and transparent. No negotiation. We offer the best market rates with full inspection reports.",
    'vehicle history': "Every vehicle comes with a comprehensive history report including previous ownership, accident history, and service records.",
    'inspection': "100-point mechanical inspection by certified technicians before listing. Report available on request.",
    'registration': "We handle all vehicle registration and transfer of ownership. Takes 3-5 business days."
}

def search_vehicles_with_nlp(analysis):
    vehicle_query = Vehicle.query.filter_by(status='available')
    
    if 'make' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.make.ilike(f"%{analysis['entities']['make']}%"))
    if 'model' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.model.ilike(f"%{analysis['entities']['model']}%"))
    if 'year' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.year >= analysis['entities']['year'] - 2, 
                                            Vehicle.year <= analysis['entities']['year'] + 2)
    if 'mileage' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.mileage <= analysis['entities']['mileage'])
    if 'fuel_type' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.fuel_type == analysis['entities']['fuel_type'])
    if 'transmission' in analysis['entities']:
        vehicle_query = vehicle_query.filter(Vehicle.transmission == analysis['entities']['transmission'])
    if analysis['price_range']:
        if analysis['price_range'].get('min'):
            vehicle_query = vehicle_query.filter(Vehicle.price >= analysis['price_range']['min'])
        if analysis['price_range'].get('max'):
            vehicle_query = vehicle_query.filter(Vehicle.price <= analysis['price_range']['max'])
    
    return vehicle_query.all()

def get_vehicle_statistics():
    available_count = Vehicle.query.filter_by(status='available').count()
    sold_count = Vehicle.query.filter_by(status='sold').count()
    
    all_available = Vehicle.query.filter_by(status='available').all()
    prices = [float(v.price) for v in all_available] if all_available else [0]
    
    under_1m = len([p for p in prices if p <= 1000000])
    under_2m = len([p for p in prices if p <= 2000000])
    under_3m = len([p for p in prices if p <= 3000000])
    under_5m = len([p for p in prices if p <= 5000000])
    
    make_counts = db.session.query(
        Vehicle.make, db.func.count(Vehicle.id)
    ).filter_by(status='available').group_by(Vehicle.make).order_by(db.func.count(Vehicle.id).desc()).limit(5).all()
    
    return {
        'total_available': available_count,
        'total_sold': sold_count,
        'min_price': min(prices) if prices else 0,
        'max_price': max(prices) if prices else 0,
        'avg_price': sum(prices) / len(prices) if prices else 0,
        'under_1m': under_1m,
        'under_2m': under_2m,
        'under_3m': under_3m,
        'under_5m': under_5m,
        'top_makes': [{'make': m[0], 'count': m[1]} for m in make_counts]
    }

def format_nlp_response(vehicles, analysis):
    if not vehicles:
        response = "❌ I couldn't find any vehicles matching your criteria.\n\n"
        if analysis['price_range'] and analysis['price_range'].get('max'):
            response += f"🔍 No vehicles found under KSh {analysis['price_range']['max']:,.0f}. "
            affordable = Vehicle.query.filter(Vehicle.status == 'available').order_by(Vehicle.price.asc()).limit(3).all()
            if affordable:
                response += f"\n\nOur most affordable vehicles start from KSh {float(affordable[0].price):,.0f}:\n"
                for v in affordable:
                    response += f"• {v.year} {v.make} {v.model} - KSh {float(v.price):,.0f}\n"
        elif 'make' in analysis['entities']:
            response += f"We don't have {analysis['entities']['make'].title()} vehicles currently. "
            other_makes = Vehicle.query.filter(Vehicle.status == 'available').limit(3).all()
            if other_makes:
                response += "Here are some alternatives:\n"
                for v in other_makes:
                    response += f"• {v.year} {v.make} {v.model} - KSh {float(v.price):,.0f}\n"
        else:
            popular = Vehicle.query.filter(Vehicle.status == 'available').limit(5).all()
            if popular:
                response += "Here are some popular vehicles from our inventory:\n"
                for v in popular:
                    response += f"• {v.year} {v.make} {v.model} - KSh {float(v.price):,.0f}\n"
        response += "\n💡 Tip: Try adjusting your search criteria or use different keywords!"
        return response
    
    response = f"✅ I found {len(vehicles)} vehicle(s) matching your request:\n\n"
    for i, v in enumerate(vehicles[:5], 1):
        response += f"{i}. **{v.year} {v.make} {v.model}**\n"
        response += f"   💰 Price: KSh {float(v.price):,.0f}\n"
        response += f"   📍 Mileage: {v.mileage:,} miles\n"
        response += f"   ⛽ Fuel: {v.fuel_type or 'N/A'} | 🔧 Transmission: {v.transmission or 'N/A'}\n\n"
    if len(vehicles) > 5:
        response += f"*And {len(vehicles) - 5} more vehicles available.*\n"
    
    if analysis['intent'] != 'general':
        response += f"\n💡 Based on your query about {analysis['intent'].replace('_', ' ')}, "
        response += "I've filtered the results to match your needs. "
        response += "Click on any vehicle to see more details!"
    
    return response

def get_general_response(query, intent, entities):
    query_lower = query.lower()
    
    for category, knowledge in PRODUCT_KNOWLEDGE.items():
        if any(term in query_lower for term in [category.replace('_', ' '), category]):
            for key, value in knowledge.items():
                if key in query_lower or any(word in query_lower for word in key.split('_')):
                    return value
    
    for keyword, answer in FAQ_DATABASE.items():
        if keyword in query_lower or get_close_matches(query_lower, [keyword], cutoff=0.6):
            return answer
    
    intent_responses = {
        'price_inquiry': "I can help you find vehicles in your budget! What price range are you looking for? (e.g., under 2 million, between 3-5 million)",
        'availability': f"We currently have {Vehicle.query.filter_by(status='available').count()} vehicles in stock. What make or model are you interested in?",
        'payment': "We accept M-Pesa (Paybill 174379), cash at our showroom, and bank transfers. Financing available through partner banks.",
        'delivery': "We deliver nationwide! Free in Nairobi. Other cities: Mombasa (KSh 25k), Kisumu (KSh 20k), Nakuru (KSh 15k).",
        'warranty': "30-day mechanical warranty included. Extended warranty available up to 1 year.",
        'test_drive': "Test drives available at our Nairobi showroom. Schedule by calling 0700-000-000.",
        'documents': "Required: National ID, KRA PIN, proof of residence, 3 months' bank statements (for financing).",
        'trade_in': "Yes! We offer free vehicle valuation. Bring your car for assessment and get instant trade-in value.",
        'contact': "📍 Location: Nairobi, Kenya\n📞 Phone: 0700-000-000\n📧 Email: sales@driveselect.co.ke\n🕐 Hours: Mon-Sat 8AM-6PM",
        'insurance': "Partner insurers: Jubilee, APA, GA Insurance. Rates: 3-5% of vehicle value annually."
    }
    
    if intent in intent_responses:
        return intent_responses[intent]
    return None

def get_unanswerable_response(query):
    unanswerable_templates = [
        f"I appreciate your question, but I don't have enough information to answer that specifically.\n\n"
        f"📋 **What I CAN help you with:**\n"
        f"• Finding vehicles by make, model, or price range\n"
        f"• Payment options (M-Pesa, Cash, Financing)\n"
        f"• Delivery information and costs\n"
        f"• Warranty and return policies\n"
        f"• Required documentation\n"
        f"• Test drive scheduling\n"
        f"• Trade-in valuations\n\n"
        f"🔄 Could you rephrase your question or ask about one of the topics above?",
        
        f"I'm still learning! While I specialize in vehicle sales, I can't answer that specific question yet.\n\n"
        f"✅ **Try asking me about:**\n"
        f"• \"What Toyota vehicles do you have?\"\n"
        f"• \"Show me cars under KSh 2 million\"\n"
        f"• \"How does M-Pesa payment work?\"\n"
        f"• \"Do you offer delivery to Mombasa?\"\n"
        f"• \"What documents do I need?\"\n\n"
        f"📞 For complex inquiries, please contact our sales team at 0700-000-000.",
        
        f"Hmm, I don't have an answer for that question in my knowledge base.\n\n"
        f"💡 **I specialize in:**\n"
        f"• Vehicle inventory and pricing\n"
        f"• Purchase process and payments\n"
        f"• Delivery and documentation\n"
        f"• Warranties and policies\n\n"
        f"Could you ask me something related to buying a vehicle? I'd love to help!"
    ]
    import random
    return random.choice(unanswerable_templates)

# ============= CHATBOT API ENDPOINTS WITH NLP =============

@app.route('/api/chatbot', methods=['POST'])
def ai_chatbot():
    data = request.json
    user_query = data.get('message', '')
    user_id = data.get('user_id') or session.get('user_id')
    
    if not user_query:
        return jsonify({'response': "Please ask me something about our vehicles!"}), 400
    
    nlp_analysis = nlp_processor.analyze_query(user_query)
    matching_vehicles = search_vehicles_with_nlp(nlp_analysis)
    
    response = None
    source = 'unknown'
    vehicle_data = []
    
    if matching_vehicles:
        response = format_nlp_response(matching_vehicles, nlp_analysis)
        source = 'nlp_vehicle_search'
        vehicle_data = [{'id': v.id, 'make': v.make, 'model': v.model, 'year': v.year, 'price': float(v.price)} for v in matching_vehicles[:3]]
    
    elif not response:
        for keyword, answer in FAQ_DATABASE.items():
            if keyword in user_query.lower() or get_close_matches(user_query.lower(), [keyword], cutoff=0.6):
                response = answer + "\n\n💡 Would you like to know more about our vehicles or payment options?"
                source = 'faq'
                break
    
    elif not response:
        for category, knowledge in PRODUCT_KNOWLEDGE.items():
            if any(term in user_query.lower() for term in [category.replace('_', ' '), category]):
                for key, value in knowledge.items():
                    if key in user_query.lower() or any(word in user_query.lower() for word in key.split('_')):
                        response = value
                        source = 'knowledge_base'
                        break
                if response:
                    break
    
    elif not response:
        response = get_general_response(user_query, nlp_analysis['intent'], nlp_analysis['entities'])
        source = 'intent_based'
    
    if not response and client.api_key and client.api_key != '':
        try:
            stats = get_vehicle_statistics()
            system_prompt = f"""You are DriveSelect AI, a helpful car sales assistant for a Kenyan dealership.

INVENTORY STATUS:
- Total vehicles: {stats['total_available']}
- Price range: KSh {stats['min_price']:,.0f} - KSh {stats['max_price']:,.0f}
- Under 2M: {stats['under_2m']} vehicles

CAPABILITIES:
- Answer questions about vehicle availability, pricing, and specs
- Explain payment (M-Pesa 174379), delivery, warranty, documentation
- Guide through purchase process
- Provide contact information

Be helpful, concise, and professional."""
            
            openai_response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.7,
                max_tokens=250
            )
            response = openai_response.choices[0].message.content
            source = 'openai'
        except Exception as e:
            print(f"OpenAI Error: {e}")
            response = None
    
    if not response:
        response = get_unanswerable_response(user_query)
        source = 'unanswerable'
        response += "\n\n📞 **Need immediate assistance?**\nOur sales team: 0700-000-000 | sales@driveselect.co.ke"
    
    if user_id:
        try:
            interaction = UserInteraction(
                user_id=int(user_id),
                vehicle_id=None,
                interaction_type=f'chat_{source}'
            )
            db.session.add(interaction)
            db.session.commit()
        except:
            pass
    
    return jsonify({
        'response': response, 
        'source': source, 
        'vehicles': vehicle_data, 
        'intent': nlp_analysis['intent'],
        'entities': nlp_analysis['entities'],
        'nlp_analysis': {
            'price_range': nlp_analysis['price_range'],
            'suggested_filters': nlp_processor.generate_suggested_filters(nlp_analysis)
        }
    })

@app.route('/api/chatbot/analyze', methods=['POST'])
def analyze_query():
    data = request.json
    query = data.get('query', '')
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    analysis = nlp_processor.analyze_query(query)
    return jsonify({
        'analysis': analysis,
        'suggested_filters': nlp_processor.generate_suggested_filters(analysis)
    })

@app.route('/api/chatbot/suggest', methods=['GET'])
def get_chat_suggestions():
    stats = get_vehicle_statistics()
    suggestions = []
    
    if stats['under_2m'] > 0:
        suggestions.append(f"Show me vehicles under KSh 2 million")
    if stats['under_3m'] > 0:
        suggestions.append(f"What cars are available under KSh 3 million?")
    if stats['under_5m'] > 0:
        suggestions.append(f"Do you have any vehicles under KSh 5 million?")
    
    top_makes = [m['make'] for m in stats['top_makes'][:3]]
    for make in top_makes:
        suggestions.append(f"What {make} vehicles do you have?")
    
    suggestions.extend([
        "How does M-Pesa payment work?",
        "What's your warranty policy?",
        "Do you offer delivery to Mombasa?",
        "What documents do I need to buy?",
        "Can I trade in my old car?",
        "Schedule a test drive",
        "Contact customer support"
    ])
    
    unique_suggestions = list(dict.fromkeys(suggestions))[:8]
    return jsonify({'suggestions': unique_suggestions})

@app.route('/api/chatbot/feedback', methods=['POST'])
def chatbot_feedback():
    data = request.json
    helpful = data.get('helpful')
    question = data.get('question')
    response = data.get('response')
    user_id = data.get('user_id')
    print(f"Chatbot Feedback - Helpful: {helpful}, Question: {question[:100] if question else 'N/A'}")
    return jsonify({'message': 'Feedback received. Thank you for helping us improve!'})

# ============= AUTHENTICATION ENDPOINTS =============

@app.route('/')
def index():
    return jsonify({"status": "online", "message": "Vehicle Sales System API is running"})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 400
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=data['password'],
        phone=data.get('phone', ''),
        role='customer'
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'Registration successful', 'user_id': new_user.id}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    login_id = data.get('username') 
    password = data.get('password')
    user = User.query.filter(or_(User.username == login_id, User.email == login_id)).first()
    if user and user.password == password:
        session['user_id'] = user.id
        return jsonify({
            'message': 'Login successful',
            'user': {'id': user.id, 'username': user.username, 'role': user.role, 'email': user.email, 'phone': user.phone}
        }), 200
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out from server'}), 200

@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    user_id = request.args.get('user_id') or session.get('user_id')
    if not user_id:
        return jsonify({'authenticated': False}), 200
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'authenticated': False}), 200
    return jsonify({'authenticated': True, 'user': {'id': user.id, 'username': user.username, 'role': user.role, 'email': user.email, 'phone': user.phone}})

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        db.session.commit()
        return jsonify({'message': 'Reset token generated.', 'debug_token': token}), 200
    return jsonify({'error': 'Email not found'}), 404

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.json
    token = data.get('token')
    new_password = data.get('password')
    user = User.query.filter_by(reset_token=token).first()
    if not user:
        return jsonify({'error': 'Invalid or expired token'}), 400
    user.password = new_password
    user.reset_token = None
    db.session.commit()
    return jsonify({'message': 'Password updated successfully'}), 200

# ============= VEHICLE ENDPOINTS =============

@app.route('/api/vehicles', methods=['GET'])
def get_vehicles():
    make = request.args.get('make')
    model = request.args.get('model')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    min_year = request.args.get('min_year')
    max_year = request.args.get('max_year')
    fuel_type = request.args.get('fuel_type')
    transmission = request.args.get('transmission')
    status = request.args.get('status', 'available')
    
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
        'id': v.id, 'make': v.make, 'model': v.model, 'year': v.year,
        'price': float(v.price), 'mileage': v.mileage, 'fuel_type': v.fuel_type,
        'transmission': v.transmission, 'engine_size': float(v.engine_size) if v.engine_size else None,
        'color': v.color, 'description': v.description, 'image_url': v.image_url,
        'status': v.status, 'created_at': v.created_at.isoformat() if v.created_at else None
    } for v in vehicles]
    return jsonify(result)

@app.route('/api/vehicles/<int:vehicle_id>', methods=['GET'])
def get_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    user_id = request.args.get('user_id') or session.get('user_id')
    if user_id:
        try:
            interaction = UserInteraction(user_id=int(user_id), vehicle_id=vehicle_id, interaction_type='view')
            db.session.add(interaction)
            db.session.commit()
        except:
            pass
    result = {
        'id': vehicle.id, 'make': vehicle.make, 'model': vehicle.model, 'year': vehicle.year,
        'price': float(vehicle.price), 'mileage': vehicle.mileage, 'fuel_type': vehicle.fuel_type,
        'transmission': vehicle.transmission, 'engine_size': float(vehicle.engine_size) if vehicle.engine_size else None,
        'color': vehicle.color, 'description': vehicle.description, 'image_url': vehicle.image_url,
        'status': vehicle.status, 'created_at': vehicle.created_at.isoformat() if vehicle.created_at else None
    }
    return jsonify(result)

@app.route('/api/vehicles/<int:vehicle_id>', methods=['PUT'])
@admin_required
def update_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    data = request.json
    try:
        if 'make' in data: vehicle.make = data['make']
        if 'model' in data: vehicle.model = data['model']
        if 'year' in data: vehicle.year = data['year']
        if 'price' in data: vehicle.price = data['price']
        if 'mileage' in data: vehicle.mileage = data['mileage']
        if 'fuel_type' in data: vehicle.fuel_type = data['fuel_type']
        if 'transmission' in data: vehicle.transmission = data['transmission']
        if 'engine_size' in data: vehicle.engine_size = data['engine_size']
        if 'color' in data: vehicle.color = data['color']
        if 'description' in data: vehicle.description = data['description']
        if 'image_url' in data: vehicle.image_url = data['image_url']
        if 'status' in data: vehicle.status = data['status']
        db.session.commit()
        return jsonify({'message': 'Vehicle updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/vehicles/<int:vehicle_id>', methods=['DELETE'])
@admin_required
def delete_vehicle(vehicle_id):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    try:
        if Purchase.query.filter_by(vehicle_id=vehicle_id).first():
            return jsonify({'error': 'Cannot delete vehicle with purchase history'}), 400
        UserInteraction.query.filter_by(vehicle_id=vehicle_id).delete()
        db.session.delete(vehicle)
        db.session.commit()
        return jsonify({'message': 'Vehicle deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ============= RECOMMENDATION ENDPOINTS =============

@app.route('/api/recommendations', methods=['POST'])
def get_recommendations():
    data = request.json
    user_id = data.get('user_id') or session.get('user_id')
    preferences = data.get('preferences', {})
    vehicles = Vehicle.query.filter_by(status='available').all()
    if not vehicles:
        return jsonify({'recommendations': [], 'total': 0, 'message': 'No vehicles available'})
    recommender.fit(vehicles)
    recommendations = recommender.recommend(preferences, n_recommendations=len(vehicles))
    result = [{
        'id': v.id, 'make': v.make, 'model': v.model, 'year': v.year, 'price': float(v.price),
        'mileage': v.mileage, 'fuel_type': v.fuel_type, 'transmission': v.transmission,
        'engine_size': float(v.engine_size) if v.engine_size else None, 'color': v.color,
        'image_url': v.image_url, 'description': v.description[:200] + '...' if v.description and len(v.description) > 200 else v.description,
        'status': v.status
    } for v in recommendations]
    return jsonify({'status': 'success', 'recommendations': result, 'total': len(result)})

# ============= PURCHASE ENDPOINTS =============

@app.route('/api/purchases/user/<int:user_id>', methods=['GET'])
def get_user_purchases(user_id):
    purchases = Purchase.query.filter_by(user_id=user_id).all()
    result = [{
        'id': p.id, 'vehicle_id': p.vehicle_id,
        'vehicle': {'make': p.vehicle.make, 'model': p.vehicle.model, 'year': p.vehicle.year, 'image_url': p.vehicle.image_url} if p.vehicle else None,
        'amount': p.amount, 'payment_status': p.payment_status, 'admin_verified': p.admin_verified,
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'verification_date': p.verification_date.isoformat() if p.verification_date else None
    } for p in purchases]
    return jsonify(result)

@app.route('/api/admin/purchases', methods=['GET'])
@admin_required
def get_admin_purchases():
    try:
        purchases = Purchase.query.order_by(Purchase.created_at.desc()).all()
        results = [{
            "id": p.id, "user_id": p.user_id, "username": p.user.username if p.user else "Unknown",
            "vehicle_id": p.vehicle_id, "vehicle_name": f"{p.vehicle.year} {p.vehicle.make} {p.vehicle.model}" if p.vehicle else "Unknown Vehicle",
            "amount": p.amount, "payment_status": p.payment_status, "payment_method": p.payment_method,
            "admin_verified": p.admin_verified, "mpesa_ref": p.mpesa_checkout_request_id,
            "date": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else None
        } for p in purchases]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

# ============= M-PESA PAYMENT ENDPOINTS =============

@app.route('/api/payments/stkpush', methods=['POST'])
def mpesa_stk_push():
    data = request.json
    phone = data.get('phone')
    amount = data.get('amount')
    vehicle_id = data.get('vehicle_id')
    user_id = data.get('user_id') or session.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    if not phone or not amount or not vehicle_id:
        return jsonify({'error': 'Missing required fields'}), 400
    
    phone = phone.replace('+', '').replace(' ', '')
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    elif not phone.startswith('254'):
        phone = '254' + phone
    
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.status != 'available':
        return jsonify({'error': 'Vehicle not available'}), 400
    
    access_token = get_mpesa_access_token()
    if not access_token:
        return jsonify({'error': 'Failed to get M-Pesa access token'}), 500
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode()).decode()
    
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE, "Password": password, "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline", "Amount": int(float(amount)), "PartyA": phone,
        "PartyB": MPESA_SHORTCODE, "PhoneNumber": phone, "CallBackURL": MPESA_CALLBACK_URL,
        "AccountReference": f"VEH_{vehicle_id}", "TransactionDesc": f"Payment for {vehicle.make} {vehicle.model}"
    }
    
    try:
        response = requests.post("https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest", json=payload, headers=headers, timeout=30)
        response_data = response.json()
        purchase = Purchase(
            user_id=user_id, vehicle_id=vehicle_id, amount=float(amount), payment_status='pending',
            payment_method='mpesa', mpesa_checkout_request_id=response_data.get('CheckoutRequestID'),
            mpesa_merchant_request_id=response_data.get('MerchantRequestID')
        )
        db.session.add(purchase)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'STK Push sent successfully', 'data': response_data, 'purchase_id': purchase.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payments/callback', methods=['POST'])
def mpesa_callback():
    try:
        data = request.json
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        purchase = Purchase.query.filter_by(mpesa_checkout_request_id=checkout_request_id).first()
        if purchase:
            purchase.mpesa_result_code = result_code
            purchase.mpesa_result_desc = result_desc
            if result_code == '0':
                purchase.payment_status = 'completed'
                purchase.admin_verified = True
                purchase.verification_date = datetime.utcnow()
                vehicle = db.session.get(Vehicle, purchase.vehicle_id)
                if vehicle:
                    vehicle.status = 'sold'
                interaction = UserInteraction(user_id=purchase.user_id, vehicle_id=purchase.vehicle_id, interaction_type='purchase')
                db.session.add(interaction)
            db.session.commit()
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})
    except Exception as e:
        return jsonify({"ResultCode": 1, "ResultDesc": "Error processing callback"}), 500

@app.route('/api/payments/manual', methods=['POST'])
def manual_payment():
    data = request.json
    vehicle_id = data.get('vehicle_id')
    user_id = data.get('user_id') or session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle or vehicle.status != 'available':
        return jsonify({'error': 'Vehicle not available'}), 400
    purchase = Purchase(user_id=user_id, vehicle_id=vehicle_id, amount=float(vehicle.price), payment_status='pending', payment_method='manual')
    db.session.add(purchase)
    db.session.commit()
    return jsonify({'message': 'Purchase request submitted.', 'purchase_id': purchase.id, 'requires_approval': True}), 201

@app.route('/api/payments/mpesa-manual', methods=['POST'])
def mpesa_manual_payment():
    data = request.json
    user_id = data.get('user_id') or session.get('user_id')
    vehicle_id = data.get('vehicle_id')
    amount = data.get('amount')
    transaction_reference = data.get('transaction_reference')
    transaction_code = data.get('transaction_code', '')
    if not user_id or not vehicle_id or not amount:
        return jsonify({'error': 'Missing required fields'}), 400
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        return jsonify({'error': 'Vehicle not found'}), 404
    if vehicle.status != 'available':
        return jsonify({'error': 'Vehicle is no longer available'}), 400
    purchase = Purchase(
        user_id=user_id, vehicle_id=vehicle_id, amount=float(amount), payment_status='pending_verification',
        payment_method='mpesa_manual', mpesa_checkout_request_id=transaction_reference,
        mpesa_result_desc=f"Transaction Code: {transaction_code}" if transaction_code else "Awaiting transaction code", admin_verified=False
    )
    db.session.add(purchase)
    db.session.commit()
    interaction = UserInteraction(user_id=user_id, vehicle_id=vehicle_id, interaction_type='purchase_initiated')
    db.session.add(interaction)
    db.session.commit()
    return jsonify({'message': 'Payment confirmation received. Your purchase is pending verification.', 'purchase_id': purchase.id, 'status': 'pending_verification'}), 201

@app.route('/api/admin/verify-purchase/<int:purchase_id>', methods=['POST'])
def verify_purchase(purchase_id):
    purchase = db.session.get(Purchase, purchase_id)
    if not purchase:
        return jsonify({'error': 'Purchase not found'}), 404
    try:
        purchase.payment_status = 'completed'
        purchase.admin_verified = True
        purchase.verification_date = datetime.utcnow()
        vehicle = db.session.get(Vehicle, purchase.vehicle_id)
        if vehicle:
            vehicle.status = 'sold'
        interaction = UserInteraction(user_id=purchase.user_id, vehicle_id=purchase.vehicle_id, interaction_type='purchase', timestamp=datetime.utcnow())
        db.session.add(interaction)
        db.session.commit()
        return jsonify({'message': 'Payment confirmed. Vehicle is now marked as SOLD.', 'purchase_id': purchase.id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/pending-payments', methods=['GET'])
@admin_required
def get_pending_payments():
    try:
        pending = Purchase.query.filter(or_(Purchase.payment_status == 'pending_verification', Purchase.payment_status == 'pending', Purchase.payment_method == 'manual', Purchase.admin_verified == False)).order_by(Purchase.created_at.desc()).all()
        result = []
        for p in pending:
            user_name = p.user.username if p.user else "Unknown User"
            vehicle_info = f"{p.vehicle.year} {p.vehicle.make} {p.vehicle.model}" if p.vehicle else "Unknown Vehicle"
            payment_display = 'Cash'
            if p.payment_method == 'mpesa_manual': payment_display = 'M-Pesa (Manual)'
            elif p.payment_method == 'mpesa': payment_display = 'M-Pesa (STK)'
            elif p.payment_method == 'manual': payment_display = 'Cash'
            result.append({'id': p.id, 'user_id': p.user_id, 'user': user_name, 'vehicle_id': p.vehicle_id, 'vehicle': vehicle_info, 'vehicle_name': vehicle_info, 'amount': float(p.amount), 'payment_status': p.payment_status, 'payment_method': payment_display, 'payment_method_raw': p.payment_method, 'transaction_ref': p.mpesa_checkout_request_id, 'admin_verified': p.admin_verified, 'date': p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else None})
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============= ADMIN ENDPOINTS =============

@app.route('/api/admin/add-vehicle', methods=['POST'])
@admin_required
def add_vehicle():
    data = request.json
    try:
        new_vehicle = Vehicle(
            make=data['make'], model=data['model'], year=data['year'], price=data['price'],
            mileage=data.get('mileage', 0), fuel_type=data.get('fuel_type'), transmission=data.get('transmission'),
            engine_size=data.get('engine_size'), color=data.get('color'), description=data.get('description'),
            image_url=data.get('image_url'), status='available'
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
    if User.query.filter(or_(User.username == data['username'], User.email == data['email'])).first():
        return jsonify({'error': 'User already exists'}), 400
    new_admin = User(username=data['username'], email=data['email'], password=data['password'], role='admin', phone=data.get('phone', ''))
    db.session.add(new_admin)
    db.session.commit()
    return jsonify({'message': f'Admin {data["username"]} created successfully'}), 201

@app.route('/api/admin/add-aux-admin', methods=['POST'])
def add_aux_admin():
    data = request.json
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400
    new_admin = User(username=username, email=email, password=password, role='admin')
    try:
        db.session.add(new_admin)
        db.session.commit()
        return jsonify({'message': f'Admin {username} registered successfully!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    users = User.query.all()
    result = [{'id': u.id, 'username': u.username, 'email': u.email, 'role': u.role, 'phone': u.phone, 'created_at': u.created_at.isoformat() if u.created_at else None, 'interaction_count': len(u.interactions)} for u in users]
    return jsonify(result)

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    try:
        UserInteraction.query.filter_by(user_id=user_id).delete()
        Purchase.query.filter_by(user_id=user_id).delete()
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'User deleted successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ============= USER ENDPOINTS =============

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'id': user.id, 'username': user.username, 'email': user.email, 'role': user.role, 'phone': user.phone, 'created_at': user.created_at.isoformat() if user.created_at else None})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    data = request.json
    try:
        if 'username' in data:
            if User.query.filter(User.username == data['username'], User.id != user_id).first():
                return jsonify({'error': 'Username already taken'}), 400
            user.username = data['username']
        if 'email' in data:
            if User.query.filter(User.email == data['email'], User.id != user_id).first():
                return jsonify({'error': 'Email already registered'}), 400
            user.email = data['email']
        if 'phone' in data:
            user.phone = data['phone']
        if 'role' in data:
            requester_id = data.get('requester_id') or session.get('user_id')
            requester = db.session.get(User, requester_id)
            if not requester or requester.role != 'admin':
                return jsonify({'error': 'Unauthorized to change role'}), 403
            user.role = data['role']
        db.session.commit()
        return jsonify({'message': 'User updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/user/orders/<int:user_id>', methods=['GET'])
def get_user_orders(user_id):
    purchases = Purchase.query.filter_by(user_id=user_id).order_by(Purchase.created_at.desc()).all()
    output = [{'id': p.id, 'vehicle': f"{p.vehicle.year} {p.vehicle.make} {p.vehicle.model}" if p.vehicle else "Unknown Vehicle", 'amount': p.amount, 'status': p.payment_status, 'method': p.payment_method, 'date': p.created_at.strftime("%b %d, %Y")} for p in purchases]
    return jsonify(output)

# ============= FAVORITES ENDPOINTS =============

@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    data = request.json
    user_id = data.get('user_id') or session.get('user_id')
    vehicle_id = data.get('vehicle_id')
    if not user_id or not vehicle_id:
        return jsonify({'error': 'user_id and vehicle_id are required'}), 400
    existing = UserInteraction.query.filter_by(user_id=user_id, vehicle_id=vehicle_id, interaction_type='favorite').first()
    if existing:
        return jsonify({'message': 'Vehicle already in favorites'}), 200
    interaction = UserInteraction(user_id=user_id, vehicle_id=vehicle_id, interaction_type='favorite')
    db.session.add(interaction)
    db.session.commit()
    return jsonify({'message': 'Added to favorites'}), 201

@app.route('/api/favorites', methods=['DELETE'])
def remove_favorite():
    data = request.json
    user_id = data.get('user_id') or session.get('user_id')
    vehicle_id = data.get('vehicle_id')
    if not user_id or not vehicle_id:
        return jsonify({'error': 'user_id and vehicle_id are required'}), 400
    interaction = UserInteraction.query.filter_by(user_id=user_id, vehicle_id=vehicle_id, interaction_type='favorite').first()
    if interaction:
        db.session.delete(interaction)
        db.session.commit()
        return jsonify({'message': 'Removed from favorites'})
    return jsonify({'error': 'Favorite not found'}), 404

@app.route('/api/favorites/<int:user_id>', methods=['GET'])
def get_favorites(user_id):
    favorites = UserInteraction.query.filter_by(user_id=user_id, interaction_type='favorite').all()
    vehicles = []
    for fav in favorites:
        vehicle = db.session.get(Vehicle, fav.vehicle_id)
        if vehicle:
            vehicles.append({'id': vehicle.id, 'make': vehicle.make, 'model': vehicle.model, 'year': vehicle.year, 'price': float(vehicle.price), 'image_url': vehicle.image_url, 'status': vehicle.status})
    return jsonify(vehicles)

# ============= CRM ENDPOINTS =============

@app.route('/api/crm/user-insights/<int:user_id>', methods=['GET'])
@admin_required
def get_user_insights(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    interactions = UserInteraction.query.filter_by(user_id=user_id).all()
    viewed_vehicles = [i.vehicle for i in interactions if i.interaction_type == 'view' and i.vehicle]
    preferences = {
        'most_viewed_make': max([v.make for v in viewed_vehicles], key=lambda x: [v.make for v in viewed_vehicles].count(x)) if viewed_vehicles else None,
        'price_range': {'min': float(min([float(v.price) for v in viewed_vehicles])) if viewed_vehicles else 0, 'max': float(max([float(v.price) for v in viewed_vehicles])) if viewed_vehicles else 0},
        'preferred_fuel_types': list(set([v.fuel_type for v in viewed_vehicles if v.fuel_type])),
        'engagement_score': len(interactions)
    }
    return jsonify({'user_id': user_id, 'preferences': preferences, 'interaction_summary': {'total_interactions': len(interactions), 'views': len([i for i in interactions if i.interaction_type == 'view']), 'favorites': len([i for i in interactions if i.interaction_type == 'favorite']), 'purchases': len([i for i in interactions if i.interaction_type == 'purchase'])}})

@app.route('/api/crm/dashboard', methods=['GET'])
@admin_required
def get_crm_dashboard():
    total_users = User.query.count()
    total_vehicles = Vehicle.query.count()
    available_vehicles = Vehicle.query.filter_by(status='available').count()
    sold_vehicles = Vehicle.query.filter_by(status='sold').count()
    total_purchases = Purchase.query.count()
    completed_purchases = Purchase.query.filter_by(payment_status='completed').count()
    total_revenue = db.session.query(db.func.sum(Purchase.amount)).filter_by(payment_status='completed').scalar() or 0
    return jsonify({'statistics': {'total_users': total_users, 'total_vehicles': total_vehicles, 'available_vehicles': available_vehicles, 'sold_vehicles': sold_vehicles, 'total_purchases': total_purchases, 'completed_purchases': completed_purchases, 'total_revenue': float(total_revenue)}})

# ============= SEARCH ENDPOINTS =============

@app.route('/api/search', methods=['GET'])
def search_vehicles():
    query = request.args.get('q', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_year = request.args.get('min_year', type=int)
    max_year = request.args.get('max_year', type=int)
    fuel_type = request.args.get('fuel_type')
    transmission = request.args.get('transmission')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    vehicle_query = Vehicle.query.filter_by(status='available')
    if query:
        vehicle_query = vehicle_query.filter(or_(Vehicle.make.ilike(f'%{query}%'), Vehicle.model.ilike(f'%{query}%'), Vehicle.description.ilike(f'%{query}%')))
    if min_price:
        vehicle_query = vehicle_query.filter(Vehicle.price >= min_price)
    if max_price:
        vehicle_query = vehicle_query.filter(Vehicle.price <= max_price)
    if min_year:
        vehicle_query = vehicle_query.filter(Vehicle.year >= min_year)
    if max_year:
        vehicle_query = vehicle_query.filter(Vehicle.year <= max_year)
    if fuel_type:
        vehicle_query = vehicle_query.filter(Vehicle.fuel_type == fuel_type)
    if transmission:
        vehicle_query = vehicle_query.filter(Vehicle.transmission == transmission)
    
    if sort_by in ['price', 'year', 'mileage', 'created_at']:
        sort_column = getattr(Vehicle, sort_by)
        vehicle_query = vehicle_query.order_by(sort_column.desc() if sort_order == 'desc' else sort_column.asc())
    
    total_count = vehicle_query.count()
    vehicles = vehicle_query.limit(limit).offset(offset).all()
    results = [{'id': v.id, 'make': v.make, 'model': v.model, 'year': v.year, 'price': float(v.price), 'mileage': v.mileage, 'fuel_type': v.fuel_type, 'transmission': v.transmission, 'engine_size': float(v.engine_size) if v.engine_size else None, 'color': v.color, 'image_url': v.image_url, 'created_at': v.created_at.isoformat() if v.created_at else None} for v in vehicles]
    return jsonify({'total': total_count, 'offset': offset, 'limit': limit, 'results': results})

# ============= STATISTICS ENDPOINTS =============

@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    total_vehicles = Vehicle.query.filter_by(status='available').count()
    make_counts = db.session.query(Vehicle.make, db.func.count(Vehicle.id)).filter_by(status='available').group_by(Vehicle.make).all()
    min_price = db.session.query(db.func.min(Vehicle.price)).filter_by(status='available').scalar() or 0
    max_price = db.session.query(db.func.max(Vehicle.price)).filter_by(status='available').scalar() or 0
    avg_price = db.session.query(db.func.avg(Vehicle.price)).filter_by(status='available').scalar() or 0
    return jsonify({'total_vehicles': total_vehicles, 'makes': [{'make': m[0], 'count': m[1]} for m in make_counts], 'price_range': {'min': float(min_price), 'max': float(max_price), 'average': float(avg_price)}})

# ============= MAIN =============

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("Database initialized.")
        
        if Vehicle.query.count() == 0:
            sample_vehicles = [
                Vehicle(make="Toyota", model="Fortuner", year=2022, price=6500000, mileage=15000, fuel_type="Diesel", transmission="Automatic", engine_size=2.8, color="White", status="available", description="Luxury SUV with premium features"),
                Vehicle(make="Honda", model="CR-V", year=2021, price=4500000, mileage=25000, fuel_type="Petrol", transmission="Automatic", engine_size=2.0, color="Black", status="available", description="Reliable family SUV"),
                Vehicle(make="Subaru", model="Forester", year=2023, price=5200000, mileage=5000, fuel_type="Petrol", transmission="CVT", engine_size=2.5, color="Blue", status="available", description="All-wheel drive adventure ready"),
                Vehicle(make="Mercedes", model="C-Class", year=2020, price=7500000, mileage=30000, fuel_type="Petrol", transmission="Automatic", engine_size=2.0, color="Silver", status="available", description="Luxury sedan with executive comfort"),
                Vehicle(make="BMW", model="X3", year=2021, price=6800000, mileage=20000, fuel_type="Diesel", transmission="Automatic", engine_size=2.0, color="Gray", status="available", description="Sporty luxury SUV"),
                Vehicle(make="Toyota", model="Vitz", year=2019, price=850000, mileage=45000, fuel_type="Petrol", transmission="Automatic", engine_size=1.0, color="Red", status="available", description="Economical city car, perfect for first-time buyers"),
                Vehicle(make="Honda", model="Fit", year=2020, price=950000, mileage=38000, fuel_type="Petrol", transmission="CVT", engine_size=1.3, color="Blue", status="available", description="Practical hatchback with excellent fuel economy"),
                Vehicle(make="Suzuki", model="Swift", year=2021, price=1200000, mileage=20000, fuel_type="Petrol", transmission="Manual", engine_size=1.2, color="White", status="available", description="Fun and reliable compact car"),
                Vehicle(make="Toyota", model="Passo", year=2018, price=750000, mileage=55000, fuel_type="Petrol", transmission="Automatic", engine_size=1.0, color="Silver", status="available", description="Affordable and reliable daily driver"),
                Vehicle(make="Nissan", model="Note", year=2019, price=880000, mileage=42000, fuel_type="Petrol", transmission="CVT", engine_size=1.2, color="Black", status="available", description="Spacious hatchback with great fuel efficiency"),
            ]
            for v in sample_vehicles:
                db.session.add(v)
            db.session.commit()
            print(f"Added {len(sample_vehicles)} sample vehicles to database.")

    port = int(os.environ.get('PORT', 5001))
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"--- SERVER LIVE ---")
    print(f"Local Access: http://localhost:{port}")
    print(f"Phone Access: http://{local_ip}:{port}")
    print(f"-------------------")
    
    app.run(debug=os.environ.get('FLASK_ENV') == 'development', host='0.0.0.0', port=port)