# VoiceTrace Backend

AI-powered multilingual financial bookkeeping for street vendors and micro-businesses.

VoiceTrace is a **voice-first financial assistant** that allows vendors to record sales, expenses, and credit transactions simply by speaking naturally in **Hindi, Marathi, English, or mixed languages**. The backend converts speech into structured financial transactions, validates them through a **multi-agent AI workflow**, stores them in **MongoDB**, and generates **business insights and next-day inventory suggestions**.

The system is designed for **low-literacy users**, **multilingual conversations**, **confidence-aware transaction extraction**, and **explainable AI**.

---

## Features

* Multilingual speech recognition (Hindi / Marathi / English / Hinglish)
* AI-powered transaction extraction
* Multi-agent validation pipeline
* Confidence-aware structured outputs
* MongoDB transaction storage
* Waste analysis and profit-loss insights
* Next-day inventory prediction
* Streaming AI updates (SSE)
* Offline-friendly frontend integration (PWA)

---

## Tech Stack

### Backend

* **FastAPI**
* **Python 3.12+**
* **LangGraph**
* **LangChain**
* **OpenAI GPT-4.1-mini**
* **OpenAI Whisper (Base + Large-v3-Turbo)**

### Database

* **MongoDB Atlas**
* **Motor (Async MongoDB Driver)**

### Storage

* **AWS S3** (voice recordings)

### Frontend

* **React**
* **Vite**
* **Progressive Web App (PWA)**

---

## High-Level Architecture

```text
Vendor speaks
      |
      v
Whisper Speech Recognition
      |
      v
FastAPI API Layer
      |
      v
LangGraph Multi-Agent Workflow
      |
      +------------------------------+
      |                              |
      v                              v
Transaction Validation        Recommendation Agent
      |                              |
      +--------------+---------------+
                     |
                     v
Transaction Extraction
                     |
                     v
MongoDB
                     |
                     v
Analytics & Insights
                     |
                     v
React PWA Frontend
```

---

# AI Agent Architecture

VoiceTrace intentionally uses **multiple specialized AI agents** instead of a single monolithic prompt. Each agent is responsible for one task only, making the system easier to debug, explain, and extend.

## Query Type Agent

Determines whether the user message represents a:

* **Sale**
* **Expense**
* **Udhar (Credit/Debt)**

---

## Validation Agent

Checks whether all required fields are present before a transaction can be stored.

### Sale

Required:

* Item
* Amount
* Quantity

### Expense

Required:

* Amount
* Expense type

### Udhar

Required:

* Person name
* Amount

If any mandatory information is missing, the transaction is **not stored**.

---

## Recommendation Agent

Activated only when required information is missing.

Uses:

* Vendor catalog
* Previous transactions
* Preferred language

Example:

> “Did you mean you sold 2 samosas for 40 rs?”

---

## Transaction Extraction Agent

Converts natural language into strongly typed **Pydantic schemas**.

Outputs structured JSON containing:

* transaction type
* amount
* item
* quantity
* confidence
* transcript
* flags

---

## Waste Analysis Agent

Analyzes previous daily records and identifies:

* frequently wasted items
* repeated losses
* actionable recommendations

---

## Next-Day Prediction Agent

Predicts tomorrow’s inventory requirements from historical sales patterns.

Example:

> “Prepare 25 samosas instead of 40.”

---

# LangGraph Workflow

```text
                 +--------------------+
                 |   User Transcript   |
                 +----------+---------+
                            |
                            v
                 +--------------------+
                 | Query Type Agent   |
                 +----------+---------+
                            |
          +----------------+----------------+
          |                |                |
          v                v                v
       Sale            Expense           Udhar
          |                |                |
          v                v                v
   Validation Agent  Validation Agent Validation Agent
          |                |                |
          +--------+-------+--------+-------+
                   |                |
             Missing Fields?        |
                   |                |
              Yes  v                |
             +-----------+          |
             | Recommendation|      |
             |     Agent     |      |
             +------+--------+      |
                    |               |
                    +-------+-------+
                            |
                            v
                 +--------------------+
                 | Extraction Agent   |
                 +----------+---------+
                            |
                            v
                      MongoDB Storage
```

---

# Project Structure

```text
voice-trace-backend/
├── agents/
│   ├── query_type_checker.py
│   ├── query_checker.py
│   ├── recommender.py
│   ├── query_maker.py
│   ├── waste_agent.py
│   ├── next_day_agent.py
│   └── text_db_agent.py
├── schemas/
├── tools/
├── api.py
├── db.py
├── llm.py
├── requirements.txt
└── README.md
```

---

# API Endpoints

## POST /api/speech_msg

Processes uploaded audio and streams AI progress updates.

**Request**

* audio file
* metadata
* language

**Response**

* streaming transcription
* validation status
* final structured transaction

---

## POST /api/recommend_msg

Processes clarification responses generated by the recommendation agent.

---

## POST /api/waste_insights

Returns AI-generated waste reduction insights.

---

## POST /api/next_day_suggestions

Returns AI-generated inventory planning suggestions.

---

# Database Collections

| Collection      | Purpose                                   |
| --------------- | ----------------------------------------- |
| vendors         | Vendor profile, language, catalog, prices |
| dailyrecords    | Sold, wasted, and unsold items            |
| saleevents      | Individual sales transactions             |
| recommendations | Clarification prompts                     |
| insights        | Generated analytics and recommendations   |

---

# Example Transaction

### User Speech

> “Becha 3 samose 60 rupaye mein”

### Extracted JSON

```json
{
  "type": "sale",
  "item": "samosa",
  "quantity": 3,
  "amount": 60,
  "pricePerUnit": 20,
  "confidence": 0.97,
  "transcript": "Becha 3 samose 60 rupaye mein",
  "flags": []
}
```

---

# Running Locally

## Clone the repository

```bash
git clone https://github.com/yourusername/voicetrace-backend.git
cd voicetrace-backend
```

## Create virtual environment

```bash
python -m venv venv
```

### Windows

```bash
venv\\Scripts\\activate
```

### macOS / Linux

```bash
source venv/bin/activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Configure environment

Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_key
MONGO_URI=your_mongodb_uri
DB_NAME=voicetrace
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=...
```

## Start the server

```bash
uvicorn api:app --reload
```

The API will be available at:

```text
http://localhost:8000
```

Swagger documentation:

```text
http://localhost:8000/docs
```

---

# Coding Principles

* Use **async MongoDB operations** everywhere.
* Return **strongly typed Pydantic models**.
* Never parse JSON manually when a schema exists.
* Never store incomplete transactions.
* Every extracted transaction must include a **confidence score**.
* Business logic belongs inside **LangGraph agents**.
* Database operations belong inside **tools/**.
* Data contracts belong inside **schemas/**.

---

# Project Goals

VoiceTrace is **not just a speech-to-text system**.

Its goal is **trustworthy AI-powered bookkeeping** for small vendors who may not maintain formal financial records.

Core principles:

* Explainability
* Reliability
* Modular AI agents
* Vendor-friendly conversations
* Multilingual accessibility
* Confidence-aware automation

---

# Roadmap

* Voice authentication
* OCR bill scanning
* AI financial advisor
* Smart inventory prediction
* Seasonal demand forecasting
* Fraud detection
* Offline synchronization
* Push notifications
* Long-term agent memory
* Multi-vendor analytics dashboard

---

# Contributing

Contributions are welcome.

Before opening a pull request:

1. Follow the existing folder structure.
2. Keep agents modular.
3. Reuse the current LangGraph workflow.
4. Prefer async implementations.
5. Maintain MongoDB Atlas compatibility.
6. Use strongly typed Pydantic models.
7. Preserve multilingual support.

---

# License

MIT License.

