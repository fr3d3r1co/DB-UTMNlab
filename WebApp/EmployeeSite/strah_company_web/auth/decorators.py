from functools import wraps
from flask import session, redirect, url_for

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            print("DEBUG: login_required - user not authenticated")
            return redirect(url_for('login'))
        print(f"DEBUG: login_required - user authenticated: {session.get('user_role')}")
        return f(*args, **kwargs)
    return decorated_function

def role_required(required_roles):
    if isinstance(required_roles, str):
        required_roles = [required_roles]
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('authenticated'):
                print("DEBUG: role_required - user not authenticated")
                return redirect(url_for('login'))
            
            user_role = session.get('user_role')
            print(f"DEBUG: role_required - checking {user_role} in {required_roles}")
            
            if not user_role or user_role not in required_roles:
                print(f"DEBUG: role_required - access denied for role {user_role}")
                return redirect(url_for('dashboard'))
                
            print(f"DEBUG: role_required - access granted for role {user_role}")
            return f(*args, **kwargs)
        return decorated_function
    return decorator