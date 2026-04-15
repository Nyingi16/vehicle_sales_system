import os
import sys
import random
from datetime import datetime

# 1. PATH CONFIGURATION
# Moves up from Testdata to root, then down into backend
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.append(BASE_DIR)

try:
    from app import app, db, User, Vehicle
except ImportError as e:
    print(f"Error: Could not find 'app.py' in {BASE_DIR}.")
    print("Ensure your folder is named 'backend' and contains app.py")
    sys.exit(1)

def seed_database():
    with app.app_context():
        # 2. DATABASE RESET
        print("Cleaning instance/vehicle_sales.db and applying new schema...")
        db.drop_all()
        db.create_all()

        # 3. CREATE DEFAULT USERS
        print("Creating default users...")
        admin = User(
            username='admin',
            email='admin@driveselect.com',
            password='admin123', # Note: In production, use hashed passwords
            role='admin',
            phone='+254711000000'
        )
        customer = User(
            username='customer',
            email='customer@driveselect.com',
            password='password123',
            role='customer',
            phone='+254722000000'
        )
        db.session.add_all([admin, customer])

        # 4. DATA POOLS FOR 200 VEHICLES
        makes_models = {
            'Toyota': [('Land Cruiser 300', 'SUV'), ('Camry', 'Sedan'), ('Supra', 'Coupe'), ('Hilux', 'Truck'), ('Vitz', 'Hatchback'), ('Rav4', 'SUV'), ('Prado', 'SUV')],
            'Mercedes-Benz': [('S-Class', 'Sedan'), ('G-Wagon', 'SUV'), ('C-Class', 'Sedan'), ('AMG GT', 'Coupe'), ('GLE', 'SUV'), ('E-Class', 'Sedan')],
            'BMW': [('X5 M', 'SUV'), ('M3', 'Sedan'), ('i7', 'Sedan'), ('M4', 'Coupe'), ('X3', 'SUV'), ('320i', 'Sedan')],
            'Audi': [('RS e-tron GT', 'Electric'), ('Q7', 'SUV'), ('A4', 'Sedan'), ('R8', 'Coupe'), ('Q5', 'SUV')],
            'Nissan': [('Patrol', 'SUV'), ('X-Trail', 'SUV'), ('Note', 'Hatchback'), ('Navara', 'Truck'), ('Sylphy', 'Sedan')],
            'Volkswagen': [('Golf GTI', 'Hatchback'), ('Tiguan', 'SUV'), ('Touareg', 'SUV'), ('Polo', 'Hatchback'), ('Passat', 'Sedan')],
            'Land Rover': [('Range Rover Vogue', 'SUV'), ('Defender 110', 'SUV'), ('Discovery', 'SUV')],
            'Subaru': [('Forester', 'SUV'), ('Impreza', 'Hatchback'), ('Outback', 'SUV'), ('WRX STI', 'Sedan')]
        }
        
        colors = ['Pearl White', 'Obsidian Black', 'Silver Metallic', 'Deep Blue', 'Candy Red', 'Champagne Gold', 'Grey']
        images = [
            'https://images.unsplash.com/photo-1583121274602-3e2820c69888',
            'https://images.unsplash.com/photo-1503376780353-7e6692767b70',
            'https://images.unsplash.com/photo-1555215695-3004980ad54e',
            'https://images.unsplash.com/photo-1494976388531-d1058494cdd8',
            'https://images.unsplash.com/photo-1502877338535-766e1452684a'
        ]

        # 5. GENERATION LOGIC
        print("Generating 200 varied vehicles for Kenyan market...")
        vehicles = []
        for i in range(200):
            make = random.choice(list(makes_models.keys()))
            model_info = random.choice(makes_models[make])
            
            year = random.randint(2016, 2026)
            # Pricing in KES (Range: 1.2M to 18M)
            price = random.randint(1200000, 18000000) 
            mileage = random.randint(0, 150000)
            fuel = random.choice(['Petrol', 'Diesel', 'Hybrid'])
            trans = random.choice(['Automatic', 'Manual'])
            
            new_vehicle = Vehicle(
                make=make,
                model=model_info[0],
                year=year,
                price=float(price),
                mileage=mileage,
                fuel_type=fuel if model_info[1] != 'Electric' else 'Electric',
                transmission=trans,
                engine_size=round(random.uniform(1.2, 5.0), 1) if model_info[1] != 'Electric' else 0.0,
                color=random.choice(colors),
                description=f"Excellent {year} {make} {model_info[0]} ({model_info[1]}). High spec, clean interior, duty fully paid.",
                image_url=random.choice(images),
                status='available'
            )
            vehicles.append(new_vehicle)

        db.session.add_all(vehicles)
        db.session.commit()
        print(f"DONE! 200 vehicles added to the database.")

if __name__ == "__main__":
    seed_database()