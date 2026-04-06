import os
import random
from datetime import datetime
from app import app, db, User, Vehicle

def seed_database():
    with app.app_context():
        # 1. Reset Database
        print("Resetting database to apply new schema...")
        db.drop_all()
        db.create_all()

        # 2. Create Default Users
        print("Creating default users...")
        admin = User(
            username='admin',
            email='admin@driveselect.com',
            password='admin123',
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

        # 3. Data Pools for 100 Vehicles
        makes_models = {
            'Toyota': [('Land Cruiser 300', 'SUV'), ('Camry', 'Sedan'), ('Supra', 'Coupe'), ('Hilux', 'Truck')],
            'Mercedes-Benz': [('S-Class', 'Sedan'), ('G-Wagon', 'SUV'), ('C-Class', 'Sedan'), ('AMG GT', 'Coupe')],
            'BMW': [('X5 M', 'SUV'), ('M3', 'Sedan'), ('i7', 'Sedan'), ('M4', 'Coupe')],
            'Audi': [('RS e-tron GT', 'Electric'), ('Q7', 'SUV'), ('A4', 'Sedan'), ('R8', 'Coupe')],
            'Tesla': [('Model S Plaid', 'Electric'), ('Model X', 'Electric'), ('Model 3', 'Electric')],
            'Ford': [('Mustang', 'Coupe'), ('F-150 Raptor', 'Truck'), ('Explorer', 'SUV')],
            'Porsche': [('911 Carrera', 'Coupe'), ('Cayenne', 'SUV'), ('Taycan', 'Electric')],
            'Lexus': [('LX 600', 'SUV'), ('ES 350', 'Sedan'), ('LC 500', 'Coupe')],
            'Land Rover': [('Range Rover Sport', 'SUV'), ('Defender', 'SUV')],
            'Volkswagen': [('Golf R', 'Hatchback'), ('Tiguan', 'SUV'), ('ID.4', 'Electric')]
        }

        colors = ['Obsidian Black', 'Pearl White', 'Marina Bay Blue', 'Guards Red', 'Daytona Grey', 'British Racing Green']
        images = [
            'https://images.unsplash.com/photo-1618843479313-40f8afb4b4d8?q=80&w=800',
            'https://images.unsplash.com/photo-1555215695-3004980ad54e?q=80&w=800',
            'https://images.unsplash.com/photo-1614200179396-2bdb77ebf81b?q=80&w=800',
            'https://images.unsplash.com/photo-1503376780353-7e6692767b70?q=80&w=800',
            'https://images.unsplash.com/photo-1594502184342-2e12f877aa73?q=80&w=800'
        ]

        vehicles = []
        print("Generating 100 varied vehicles...")

        for i in range(100):
            # Pick a random make and its associated models
            make = random.choice(list(makes_models.keys()))
            model_info = random.choice(makes_models[make])
            
            # Randomize specs
            year = random.randint(2018, 2025)
            price = random.randint(25000, 220000)
            mileage = random.randint(0, 80000)
            fuel = random.choice(['Petrol', 'Diesel', 'Electric', 'Hybrid'])
            trans = random.choice(['Automatic', 'Manual', 'DCT'])
            
            new_vehicle = Vehicle(
                make=make,
                model=model_info[0],
                year=year,
                price=float(price),
                mileage=mileage,
                fuel_type=fuel if model_info[1] != 'Electric' else 'Electric',
                transmission=trans,
                engine_size=round(random.uniform(1.6, 5.0), 1) if model_info[1] != 'Electric' else 0.0,
                color=random.choice(colors),
                description=f"Exquisite {make} {model_info[0]} from the {year} lineup. Quality guaranteed.",
                image_url=random.choice(images)
            )
            vehicles.append(new_vehicle)

        db.session.add_all(vehicles)
        db.session.commit()
        print(f"Success: Database reset and seeded with 100 vehicles and 2 users.")

if __name__ == '__main__':
    seed_database()