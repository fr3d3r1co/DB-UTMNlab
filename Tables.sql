DROP TABLE IF EXISTS departments CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS car_brands CASCADE;
DROP TABLE IF EXISTS car_models CASCADE;
DROP TABLE IF EXISTS policy_statuses CASCADE;
DROP TABLE IF EXISTS policies CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP TABLE IF EXISTS notifications CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;


-- отделs компании
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE, -- e.g., 'Отдел продаж', 'Управление рисков'
	manager_id INT
);

-- table сотрудников
CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    department_id INT NOT NULL REFERENCES departments(department_id) ON DELETE RESTRICT,
    phone VARCHAR(11)  UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
	
    -- Поля для системы аутентификации
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- table клиентов (физические лица)
CREATE TABLE clients (
    client_id SERIAL PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100),
    -- Паспортные данные (хранение ПДн)
    passport_series VARCHAR(4),
    passport_number VARCHAR(6),
    birth_date DATE,
    registration_address TEXT, -- Адрес регистрации
    -- Водительское удостоверение
    driver_license_series VARCHAR(4),
    driver_license_number VARCHAR(6),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Справочник марок автомобилей
CREATE TABLE car_brands (
    brand_id SERIAL PRIMARY KEY,
    brand_name VARCHAR(100) NOT NULL UNIQUE -- 'Toyota', 'BMW'
);

-- Справочник моделей автомобилей (связь с маркой)
CREATE TABLE car_models (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL, -- 'Camry', 'X5'
    brand_id INT NOT NULL REFERENCES car_brands(brand_id) ON DELETE CASCADE
);

-- Справочник статусов полиса
CREATE TABLE policy_statuses (
    status_id SERIAL PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL UNIQUE -- 'Оформлен', 'Активен', 'Аннулирован', 'Истек'
);

-- Основная таблица полисов
CREATE TABLE policies (
    policy_id SERIAL PRIMARY KEY,
    -- Ссылка на статус (денормализация для избежания JOIN в частых запросах)
    status_id INT NOT NULL REFERENCES policy_statuses(status_id) ON DELETE RESTRICT,
    
	-- Данные о сотруднике и отделе на момент создания (историчность + денормализация)
    created_by_employee_id INT NOT NULL REFERENCES employees(employee_id) ON DELETE RESTRICT,
    created_in_department_id INT NOT NULL REFERENCES departments(department_id) ON DELETE RESTRICT,
    
	-- Реквизиты полиса
    policy_number VARCHAR(50) NOT NULL UNIQUE, -- Уникальный номер полиса
    cost DECIMAL(15,2) NOT NULL CHECK (cost >= 0), -- Стоимость
    start_date DATE NOT NULL, -- Начало действия
    end_date DATE NOT NULL, -- Окончание действия
    conclusion_date DATE NOT NULL DEFAULT CURRENT_DATE, -- Дата заключения
    
	-- Данные об объекте страхования (автомобиль)
    car_brand_id INT NOT NULL REFERENCES car_brands(brand_id) ON DELETE RESTRICT,
    car_model_id INT NOT NULL REFERENCES car_models(model_id) ON DELETE RESTRICT,
    car_vin VARCHAR(50), -- VIN-номер
    car_reg_number VARCHAR(20), -- Гос. номер
    
	-- Владелец и дополнительные водители
    owner_client_id INT NOT NULL REFERENCES clients(client_id) ON DELETE RESTRICT,
    additional_drivers JSONB, -- JSON массив client_id для гибкости (оправданная денормализация)
    
	-- Системные поля
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_dates CHECK (start_date <= end_date)
);

-- ТАБЛИЦА ДОКУМЕНТОВ (Ключевая по заданию)
CREATE TABLE documents (
    document_id SERIAL PRIMARY KEY,
    -- Привязка к полису (если документ - это полис)
    policy_id INT REFERENCES policies(policy_id) ON DELETE CASCADE,

	-- Данные о сотруднике и отделе на момент создания (историчность + денормализация)
    created_by_employee_id INT NOT NULL REFERENCES employees(employee_id) ON DELETE RESTRICT,
    created_in_department_id INT NOT NULL REFERENCES departments(department_id) ON DELETE RESTRICT,
	
	-- Описание документа
    file_name VARCHAR(500) NOT NULL, 
    description TEXT,
    stored_file_path TEXT NOT NULL UNIQUE, -- Путь к файлу в файловой системе / S3 хранилище
    file_size BIGINT, -- Размер файла в байтах
    --mime_type VARCHAR(100), -- MIME-тип
    
	-- Атрибуты доступа и аудита
    confidentiality_level INT NOT NULL DEFAULT 0 CHECK (confidentiality_level >= 0), -- 0-публичный, 1-ДСП, 2-только начальники
    created_at TIMESTAMPTZ DEFAULT NOW()	
);

-- Таблица для уведомлений об изменениях
CREATE TABLE notifications (
    notification_id SERIAL PRIMARY KEY,
    document_id INT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    changed_by_employee_id INT NOT NULL REFERENCES employees(employee_id) ON DELETE CASCADE,
    change_description TEXT, -- 'Было изменено поле X'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

