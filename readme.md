✈️ QA Autopilot: Un Protocolo de Contexto de Modelo (MCP) para Jira y Gemini
Una herramienta de línea de comandos (CLI) que implementa el concepto de Protocolo de Contexto de Modelo (MCP). Esta herramienta actúa como un bridge que conecta Jira (como servidor de conocimiento) con Google Gemini (vía Vertex AI) para la generación de casos de prueba.

La Analogía: El Piloto Automático
Como piloto comercial, sé que el piloto automático no vuela el avión solo. El piloto sigue al mando: monitorea los sistemas, gestiona el plan de vuelo y toma las decisiones críticas. El piloto automático se encarga del trabajo pesado y repetitivo, permitiendo al piloto enfocarse en lo estratégico.

Este proyecto aplica el mismo principio al Quality Assurance.

¿Cuál es el Problema?
La creación manual de casos de prueba en Jira es una de las tareas más necesarias pero también más tediosas del ciclo de vida del software. Consume un tiempo valioso que los analistas de QA podrían dedicar a tareas de mayor impacto, como pruebas exploratorias, diseño de estrategias de automatización o análisis de riesgos complejos.

La Solución: "QA Autopilot" como un MCP
Inspirado en el concepto de Protocolo de Contexto de Modelo (MCP) —que permite a los modelos conectarse a servidores de conocimiento—, esta herramienta no busca reemplazar al analista de QA, sino potenciarlo.

Actúa como un bridge inteligente que se ejecuta con un solo comando:

Recibe un ID de Historia de Usuario (HU) de Jira desde la terminal.

Actúa como MCP: Se conecta a la API de Jira (el "servidor de conocimiento") para extraer el contexto completo (descripción, criterios de aceptación).

Consulta al Modelo: Envía ese contexto a Google Gemini con un prompt de QA.

Genera un conjunto detallado de casos de prueba (en formato Gherkin).

Crea automáticamente los issues de tipo "Test" en Jira/Xray, enlazándolos a la HU original.

El resultado: en lugar de pasar horas escribiendo TCs, el analista de QA (el "piloto") solo tiene que revisar, ajustar y aprobar los TCs generados, ahorrando una cantidad significativa de tiempo y esfuerzo.

Arquitectura y Flujo de Trabajo
El flujo de la aplicación es el siguiente:

Inicio: Un usuario (Analista de QA) ejecuta el script run_mcp.py desde la terminal, pasando un ID de issue (ej: python run_mcp.py --issue PROJ-123).

Extracción (Jira): El script usa el módulo src/core/jira.py para conectarse a la API de Jira y obtener los detalles de la PROJ-123 (título, descripción, criterios de aceptación).

Generación (Gemini): El script pasa esta información al módulo src/core/llm.py, que construye un prompt y lo envía a la API de Gemini en Vertex AI.

Respuesta (Gemini): Gemini devuelve una respuesta estructurada (ej: JSON con una lista de TCs en Gherkin).

Creación (Jira/Xray): El script toma estos TCs y, usando src/core/jira.py nuevamente, crea un issue de tipo "Test" por cada caso de prueba en Jira, enlazándolos automáticamente a la HU PROJ-123.

Fin: El script imprime la confirmación en la terminal. El Analista de QA ya puede ver sus TCs creados en Jira.

🛠️ Tech Stack
Backend: Python 3.10+

Inteligencia Artificial: Google Gemini vía Google Cloud Vertex AI

Integración: Jira REST API (usando la librería requests)

CLI: argparse de Python.

Configuración: python-dotenv para manejo seguro de credenciales.

🚀 Puesta en Marcha (Getting Started)
Sigue estos pasos para configurar y ejecutar el proyecto en tu máquina local.

1. Prerrequisitos
Python 3.10 o superior.

Una cuenta de Jira Cloud con Xray instalado.

Permisos para crear Tokens de API en Atlassian.

Un proyecto de Google Cloud con la API de Vertex AI habilitada y las credenciales de autenticación (un archivo JSON de cuenta de servicio).

2. Instalación
Clona este repositorio:

git clone https://github.com/tu-usuario/mcp-xray-python.git
cd mcp-xray-python
Crea un entorno virtual:

python -m venv venv
Activa el entorno virtual:

En macOS/Linux: source venv/bin/activate

En Windows: .\venv\Scripts\activate

Instala las dependencias:

pip install -r requirements.txt
3. Configuración de Credenciales
Este proyecto usa un archivo .env para manejar información sensible de forma segura.

Crea una copia del archivo de ejemplo:

cp .env.example .env
Abre el archivo .env con tu editor de texto y rellena TODAS las variables:

# Configuración de JIRA
JIRA_URL="https://tu-instancia.atlassian.net"
JIRA_USER="tu-email-de-jira@dominio.com"
JIRA_API_TOKEN="TU_API_TOKEN_DE_JIRA_AQUI"
JIRA_PROJECT_KEY="PROJ" # La clave de tu proyecto en Jira (ej: 'TEST')

# Configuración de Google Vertex AI (Gemini)
VERTEX_AI_PROJECT_ID="tu-id-de-proyecto-gcp"
VERTEX_AI_LOCATION="us-central1" # o la región que estés usando

# Ruta al archivo JSON de credenciales de Google Cloud
# Asegúrate de que esta ruta sea correcta
GOOGLE_APPLICATION_CREDENTIALS="./ruta/a/tu/archivo-credenciales.json"

# Configuración del Modelo Gemini
GEMINI_MODEL_NAME="gemini-1.5-pro" # o el modelo que prefieras
🏁 Uso
Una vez que tu entorno virtual esté activado (venv) y tu archivo .env esté configurado, la ejecución es tan simple como correr el script run_mcp.py con el ID del issue de Jira.

# Ejemplo de uso básico:
python run_mcp.py --issue ALL-8296

# Ejemplo borrando tests obsoletos (en lugar de solo etiquetarlos):
python run_mcp.py --issue ALL-8296 --delete-obsolete

🧪 Pruebas Unitarias
El proyecto incluye un conjunto de pruebas unitarias para asegurar la calidad y estabilidad del código en los módulos principales.

1.  **Instalar dependencias de desarrollo:**
    Asegúrate de tener `pytest` instalado (incluido en `requirements.txt`):
    ```bash
    pip install -r requirements.txt
    ```

2.  **Ejecutar las pruebas:**
    Desde la carpeta raíz del proyecto, simplemente ejecuta:
    ```bash
    pytest
    ```

🤝 Contribuciones
¡Las contribuciones son bienvenidas! Si tienes ideas para mejorar la herramienta, optimizar los prompts de Gemini o añadir nuevas funcionalidades, por favor:

Haz un Fork del proyecto.

Crea tu rama de feature (git checkout -b feature/MejoraIncreible).

Haz commit de tus cambios (git commit -m 'Añade MejoraIncreible').

Haz push a la rama (git push origin feature/MejoraIncreible).

Abre un Pull Request.

📄 Licencia
Este proyecto está bajo la Licencia MIT. Consulta el archivo LICENSE para más detalles.