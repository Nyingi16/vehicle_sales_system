from app import app, db, User

def list_all_users():
    with app.app_context():
        print("-" * 50)
        print(f"{'ID':<4} | {'Username':<15} | {'Role':<10} | {'Password (Plain)':<20}")
        print("-" * 50)
        
        users = User.query.all()
        if not users:
            print("No users found in the database.")
        
        for user in users:
            print(f"{user.id:<4} | {user.username:<15} | {user.role:<10} | {user.password:<20}")
        print("-" * 50)

if __name__ == "__main__":
    list_all_users()