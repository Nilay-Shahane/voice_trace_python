# VoiceTrace Backend

## Project Overview

VoiceTrace is a voice-first financial assistant designed for informal vendors such as street vendors, small shop owners, and micro-businesses.

Instead of manually writing expenses and sales, vendors simply speak naturally in Hindi, Marathi, English, or mixed languages.

The backend converts speech into structured financial transactions, validates them using multiple AI agents, stores them in MongoDB, and generates business insights.

The project prioritizes:

- Low literacy usability
- Multilingual interaction
- Explainable AI
- Confidence-aware transaction extraction
- Business intelligence
- Offline-first frontend support (PWA)

---

# Tech Stack

Backend
- FastAPI
- Python 3.12+
- LangGraph
- LangChain
- OpenAI GPT-4.1-mini
- Whisper (Base + Large-v3-Turbo)

Database
- MongoDB Atlas
- Motor (Async MongoDB Driver)

Storage
- AWS S3 (voice recordings)

Frontend
- React
- Vite
- Progressive Web App

---

# High Level Flow

Vendor speaks

↓

Whisper Speech Recognition

↓

FastAPI

↓

LangGraph

↓

Transaction Classification

↓

Validation Agent

↓

Recommendation Agent (if required)

↓

Transaction Extraction

↓

MongoDB

↓

Analytics

↓

Frontend

---

# AI Architecture

The system is intentionally built using multiple AI agents instead of a single prompt.

Every agent has one responsibility.

Current agents include:

## Query Type Agent

Purpose

Determines whether the user's message is

- Sale
- Expense
- Udhar

---

## Validation Agent

Checks whether required fields are present.

Examples

Sale

Requires

- Item
- Amount
- Quantity

Expense

Requires

- Amount
- Expense Type

Udhar

Requires

- Person Name
- Amount

If information is missing, the transaction is NOT stored.

---

## Recommendation Agent

Runs only when required information is missing.

Uses

- Vendor catalog
- Previous items
- Vendor language

Generates conversational clarification questions.

Example

"Did you mean you sold 2 samosas for 40 rs?"

---

## Transaction Extraction Agent

Converts natural language into structured JSON using Pydantic schemas.

Returns

- transaction type
- amount
- item
- quantity
- confidence
- transcript
- flags

---

## Waste Analysis Agent

Reads previous daily records.

Identifies

- wasted items
- repeated losses
- actionable suggestions

---

## Next Day Prediction Agent

Analyzes previous sales.

Suggests tomorrow's stock.

Example

Prepare 25 samosas instead of 40.

---

# API Endpoints

POST /api/speech_msg

Receives

- audio
- metadata

Returns

- streaming AI updates
- final transaction

---

POST /api/recommend_msg

Processes clarification answers.

---

POST /api/waste_insights

Returns waste reduction suggestions.

---

POST /api/next_day_suggestions

Returns AI stock planning suggestions.

---

# Database Collections

vendors

Stores

- language
- catalog
- prices

dailyrecords

Stores

- sold items
- wasted items
- unsold items

saleevents

Stores all sales.

recommendations

Stores clarification recommendations.

insights

Stores computed analytics.

---

# Coding Conventions

Always use async MongoDB.

Always return structured Pydantic models.

Never parse JSON manually if a schema exists.

Never store incomplete transactions.

Confidence must always be included.

Business logic belongs inside LangGraph agents.

Database code belongs inside tools/.

Schemas belong inside schemas/.

---

# Project Goals

The objective is not just speech recognition.

The objective is trustworthy financial bookkeeping using AI.

The backend focuses on

- Explainability
- Reliability
- Modular AI
- Vendor-friendly conversations

---

# Future Roadmap

- Voice authentication
- OCR bill scanning
- AI financial advisor
- Smart inventory prediction
- Seasonal demand forecasting
- Fraud detection
- Offline synchronization
- Push notifications
- Agent memory
- Multi-vendor analytics

---

# Notes for Claude

When generating code:

- Prefer existing project architecture.
- Reuse current LangGraph workflow.
- Keep agents modular.
- Avoid introducing new frameworks unless requested.
- Follow existing folder structure.
- Use async functions wherever possible.
- Maintain compatibility with MongoDB Atlas.
- Prefer strongly typed Pydantic models.
- Preserve multilingual support.

Always improve the existing architecture instead of replacing it.