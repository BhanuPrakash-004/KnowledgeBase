# KMRL InsightEngine

This project is an AI-powered document intelligence platform built to ingest, understand, and deliver actionable insights from various documents. It was developed as part of a hackathon to solve document management challenges for organizations like Kochi Metro Rail Limited (KMRL).

## Features

-   **File Ingestion**: Upload documents (PDF, TXT, PNG, JPG).
-   **AI Analysis**: Automatically generates a summary, extracts key action items, and suggests a relevant department/role for handling the document.
-   **Persistent Knowledge Base**: Documents are processed and stored in a searchable vector database using FAISS.
-   **Conversational Q&A**: A chat interface to ask questions about any content within the uploaded documents.
-   **Automation Ready**: Triggers n8n webhooks with the analysis results to enable downstream automation workflows.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

1.  **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
2.  **Ollama**: You must have Ollama installed and running. [Download Ollama](https://ollama.com/)
3.  **Tesseract OCR**: This is required for extracting text from images.
    -   **Windows**: Download and install from [here](https://github.com/UB-Mannheim/tesseract/wiki). Make sure to add the installation path to your system's `PATH` environment variable.
    -   **macOS**: `brew install tesseract`
    -   **Linux (Debian/Ubuntu)**: `sudo apt-get install tesseract-ocr`
4.  **Poppler**: This is required by the `pdf2image` library to handle PDFs.
    -   **Windows**: Follow the instructions [here](https://github.com/oschwartz10612/poppler-windows/releases/). You will need to add the `\bin` directory to your `PATH`.
    -   **macOS**: `brew install poppler`
    -   **Linux (Debian/Ubuntu)**: `sudo apt install poppler-utils`

## Setup and Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/BhanuPrakash-004/SIH.git
    cd backend-python
    ```

2.  **Pull Required Ollama Models**
    Open your terminal and pull the LLM and embedding models that the application uses:
    ```bash
    ollama pull llama3
    ollama pull mxbai-embed-large
    ```
    Ensure Ollama is running in the background.

3.  **Create and Activate a Virtual Environment**
    It is highly recommended to use a virtual environment to manage project dependencies.

    * **On macOS/Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

    * **On Windows:**
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```

4.  **Install Dependencies**
    With your virtual environment activated, install all the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

Once the setup is complete, you can start the FastAPI backend server:

```bash
python main.py
```

The server will start, it is running on `http://localhost:8000`. You can now access the API endpoints.

### Start the Frontend

In a new terminal, navigate to the `frontend-react` directory and start the development server:

```bash
cd ../frontend-react
npm install # Install frontend dependencies if you haven't already
npm run dev
```

The frontend application will typically open in your browser at `http://localhost:5173` (or another port if 5173 is in use).
 