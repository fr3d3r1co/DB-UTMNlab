import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config

def get_db_connection():
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        database=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        cursor_factory=RealDictCursor
    )
    return conn

def execute_query(query, params=None, fetch=True):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute(query, params)
        if fetch:
            if query.strip().upper().startswith('SELECT'):
                result = cur.fetchall()
            else:
                result = None
            conn.commit()
        else:
            result = None
            conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
    
    return result