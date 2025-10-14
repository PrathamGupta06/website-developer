# Website Developer API

An automated web application builder API that accepts JSON requests and generates complete web applications, pushes them to GitHub repositories, and enables GitHub Pages hosting.

## Features

- **FastAPI-based REST API** with async processing
- **Secret validation** for secure access
- **GitHub integration** for automatic repository creation and Pages deployment
- **Background processing** with retry logic for evaluation callbacks
- **Attachment handling** with data URI decoding
- **Extensible architecture** ready for AI/LLM integration

## Quick Start

### Prerequisites

- Python 3.12+
- GitHub Personal Access Token (for repository creation)
- A secret key for API authentication

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd website-developer
```

2. Install dependencies:
```bash
pip install -e .
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your GitHub token and API secret
```

4. Run the API:
```bash
python main.py
```

The API will be available at `http://localhost:8000`

## API Endpoints

### `POST /build`

Main endpoint for building web applications.

**Request Body:**
```json
{
  "email": "student@example.com",
  "secret": "your-api-secret",
  "task": "captcha-solver-123",
  "round": 1,
  "nonce": "ab12-...",
  "brief": "Create a captcha solver that handles ?url=https://.../image.png",
  "checks": [
    "Repo has MIT license",
    "README.md is professional",
    "Page displays captcha URL passed at ?url=...",
    "Page displays solved captcha text within 15 seconds"
  ],
  "evaluation_url": "https://example.com/notify",
  "attachments": [
    {
      "name": "sample.png",
      "url": "data:image/png;base64,iVBORw..."
    }
  ]
}
```

**Response:**
```json
{
  "status": "accepted",
  "message": "Build request accepted and processing started",
  "task": "captcha-solver-123",
  "round": 1
}
```

### `GET /health`

Health check endpoint.

### `GET /`

Root endpoint returning API status.

## How It Works

1. **Request Validation**: Validates the provided secret against the configured API secret
2. **Attachment Processing**: Decodes data URI attachments and saves them
3. **Code Generation**: Generates application code based on the brief (skeleton implementation ready for AI integration)
4. **Repository Creation**: Creates a new GitHub repository with a unique name
5. **File Upload**: Pushes all generated files to the repository
6. **GitHub Pages**: Enables GitHub Pages for the repository
7. **Evaluation Callback**: Posts results to the evaluation URL with retry logic

## Configuration

Environment variables:

- `GITHUB_TOKEN`: GitHub Personal Access Token (required for repo creation)
- `API_SECRET`: Secret key for API authentication
- `HOST`: API host (default: 0.0.0.0)
- `PORT`: API port (default: 8000)

## Architecture

```
├── main.py          # FastAPI application, routes, and core business logic
├── models.py        # Pydantic models for request/response validation
└── .env.example     # Environment configuration template
```

## Development

### Running in Development Mode

```bash
python main.py
```

This starts the server with auto-reload enabled.

### Testing the API

```bash
curl -X POST http://localhost:8000/build \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "secret": "your-secret",
    "task": "test-task",
    "round": 1,
    "nonce": "test-nonce",
    "brief": "Create a simple web page",
    "checks": ["Has index.html"],
    "evaluation_url": "https://httpbin.org/post",
    "attachments": []
  }'
```

## Extending for AI Integration

The `generate_application_code` method in `main.py` is designed to be replaced with actual AI/LLM integration:

```python
async def generate_application_code(self, brief: str, checks: list, attachments_data: list):
    # Replace this section with your AI/LLM integration
    # Example: OpenAI GPT, Claude, or local models
    
    ai_response = await your_ai_service.generate_code(
        brief=brief,
        requirements=checks,
        attachments=attachments_data
    )
    
    return ai_response.files
```

## Production Deployment

For production deployment:

1. Set secure environment variables
2. Use a production WSGI server (e.g., Gunicorn)
3. Set up proper logging and monitoring
4. Configure rate limiting and authentication
5. Use HTTPS
6. Set up database for request tracking (optional)

## License

MIT License - see LICENSE file for details.