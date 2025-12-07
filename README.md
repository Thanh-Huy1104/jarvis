# Jarvis

![GitHub Banner](./banner.png)

<p align="center">
  <strong>A voice-powered AI assistant.</strong>
</p>

## About

Jarvis is a conversational AI assistant that uses various services to understand and respond to voice commands. It is built with a modular architecture, allowing for easy integration and replacement of components.

## Features

- **Voice-to-Text (STT):** Converts spoken language into text using Whisper.
- **Language Model (LLM):** Processes text and generates responses using vLLM.
- **Text-to-Speech (TTS):** Converts text responses back into speech using Kokoro.
- **Memory:** Remembers previous conversations using Mem0.
- **Modular Design:** Easily swap out adapters for different services.

## Architecture

The project is structured as follows:

- `app/`: The core application logic.
  - `adapters/`: Connectors to external services (LLM, STT, TTS, Memory).
  - `api/`: The API for interacting with the application.
  - `core/`: The main application orchestration and state management.
  - `domain/`: Business logic and data structures.
- `servers/`: Different ways to run the application.
  - `desktop/`: A desktop server for running the application.

## Getting Started

### Prerequisites

- Python 3.10+
- Pip

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/Thanh-Huy1104/jarvis.git
    cd jarvis
    ```
2.  Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

To start the desktop server:

```bash
python uvicorn app.main:app --reload --port 8080
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
