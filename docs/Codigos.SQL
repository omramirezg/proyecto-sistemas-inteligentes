-- ============================================================================
-- 1. TABLAS MAESTRAS (Catálogos estáticos de configuración)
-- ============================================================================

CREATE TABLE maestro_equipos (
    id_planta VARCHAR(10),              -- Ej: '001' (Planta1) o '002' (Planta2)
    id_maquina VARCHAR(50),             -- Identificador del equipo (Ej: '301', '302', '303', '304', '305')
    capacidad_nominal FLOAT,            -- Capacidad máxima de producción (Ton/Hora)
    corriente_vacio FLOAT,              -- Amperaje base del motor sin carga (A)
    corriente_carga_minima FLOAT,       -- Amperaje mínimo para considerar que está la maquina On
    PRIMARY KEY (id_planta, id_maquina)
);

CREATE TABLE maestro_personal (
    id_empleado VARCHAR(50) PRIMARY KEY,-- Identificador único (Ej: 'EMP-001')
    nombre_completo VARCHAR(100),       -- Nombre del operario o supervisor
    id_planta VARCHAR(10),              -- Planta a la que pertenece
    rol VARCHAR(50),                    -- Ej: 'Operario', 'Supervisor'
    id_maquina_asignada VARCHAR(50),    -- Máquina responsable (o 'TODAS' para supervisores)
    dias_laborales VARCHAR(50),         -- Formato de días de turno (Ej: "1,2,3,4,5,6,7")
    hora_inicio_turno TIME,             -- Hora local de entrada
    hora_fin_turno TIME,                -- Hora local de salida
    numero_celular VARCHAR(20),         -- Celular con código de país para WhatsApp (Ej: '+57...')
    recibe_alertas BOOLEAN,             -- 1 = Activo para notificaciones, 0 = Inactivo
    recibe_prescriptivo BOOLEAN,        -- 1 = Recibe nota de voz del LLM, 0 = Solo texto
    recibe_pdf BOOLEAN                  -- 1 = Recibe reporte adjunto, 0 = No
);

CREATE TABLE maestro_formulas (
    id_planta VARCHAR(10),              
    id_formula VARCHAR(20),             -- Código corto de la fórmula (Ej: '3360')
    codigo_producto VARCHAR(50),        -- Nomenclatura del producto (Ej: 'ZB1')
    t_min FLOAT,                        -- Temperatura mínima permitida (°C)
    t_max FLOAT,                        -- Temperatura máxima permitida (°C)
    p_min FLOAT,                        -- Presión de vapor mínima (PSI)
    p_max FLOAT,                        -- Presión de vapor máxima (PSI)
    pqf FLOAT,                          -- Pellet Quality Factor (Escala de aglutinación)
    humedad_objetivo FLOAT,             -- Meta de humedad (%) para el modelo IA
    durabilidad_objetivo FLOAT,         -- Meta de PDI (%) para el modelo IA
    PRIMARY KEY (id_planta, id_formula)
);

-- ============================================================================
-- 2. TABLAS TRANSACCIONALES (Telemetría en tiempo real)
-- ============================================================================
-- Se Ejempliza para Planta 001, pero se debe replicar para Planta 002 con el mismo esquema y solo cambiando el nombre de la tabla a "telemetria_planta_002"
CREATE OR REPLACE TABLE telemetria_planta_001 (
    -- 1. CONTEXTO Y LLAVES (Todo en VARCHAR para asegurar cruces perfectos)
    fecha_registro TIMESTAMP_NTZ,       -- NTZ: No Time Zone (Hora local del PLC)
    id_planta VARCHAR(10),              -- Ej: '001'
    id_maquina VARCHAR(50),             -- Ej: '301', '302', '303', '304', '305'
    id_formula VARCHAR(20),             -- Ej: '3360'
    numero_orden VARCHAR(50),           -- Ej: '61984'
    
    -- 2. VARIABLES FÍSICAS (En FLOAT para soportar decimales de alta precisión)
    corriente FLOAT,                    -- Amperaje del motor principal
    temp_acond FLOAT,                   -- Temperatura en °C
    presion_vapor FLOAT,                -- Presión en PSI/Bar
    vapor FLOAT,                        -- Caudal o flujo de vapor
    porcentaje_vapor FLOAT,             -- % de apertura válvula
    tiempo_proceso FLOAT,               -- Segundos de retención / residencia
    kw_h_proceso FLOAT,                 -- Energía consumida
    
    -- 3. ESTADOS Y METADATOS
    retornando NUMBER(1,0),             -- 0 = Producción Normal, 1 = Desvío/Falla
    
    -- 4. ETIQUETAS DE MACHINE LEARNING (Targets para predicción)
    humedad_real FLOAT,                 -- % Humedad medida en laboratorio
    durabilidad_real FLOAT              -- % PDI medido en laboratorio
);