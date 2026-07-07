<div align="center">
  <img src="frontend/assets/logo.png" alt="MahaFund Brief Logo" height="80">
  <h1>MahaFund Brief</h1>
  <p><b>AI-Powered Real Estate Due Diligence & Funding Intelligence</b></p>
  <p><i>Developed as part of agency work for <a href="https://arisetoascend.com">Arise To Ascend</a></i></p>
</div>

<br/>

## The Problem
Real estate financing requires extensive due diligence, particularly verifying regulatory compliance, cost estimates, and developer history. Manually extracting data from state portals (like Maharashtra RERA), cross-referencing market sites (99acres, Housing.com), and reviewing complex financial PDFs (CA Certificates) takes analysts hours per project.

## The Solution
**MahaFund Brief** is an agentic AI platform that automates this entire pipeline. By entering a single RERA Registration Number (e.g., `P51700000002`), the system orchestrates a swarm of intelligent agents to scrape, parse, and analyze the data, delivering a comprehensive, 10-point scored **DOCX Funding Brief** in under two minutes.

---

## 🧠 AI Engineering & Tech Stack

This project demonstrates advanced AI engineering techniques, moving beyond simple wrappers to orchestrate complex, stateful agent workflows.

### Agentic Orchestration (`LangGraph`)
The core pipeline is a directed acyclic graph (DAG) managed by **LangGraph**. It controls the sequential and conditional flow of multiple specialized agents (MahaRERA Agent, Zaubacorp Agent, 99acres Agent, Housing.com Agent), maintaining a shared state and gracefully handling fallbacks if an agent fails.

### Multimodal Document Extraction (`Gemini 1.5 Pro Vision`)
Instead of relying on fragile text-parsing libraries (like PyMuPDF) to extract tabular financial data from scanned CA Certificates, the platform passes the raw PDF bytes directly to **Gemini 1.5 Pro Vision**. The LLM visually interprets the tables to accurately extract exact `Land Cost`, `Construction Cost`, and `Projected Revenue`.

### Headless Web Scraping & CAPTCHA Solving (`Playwright` + LLM)
The MahaRERA portal is protected by dynamic image CAPTCHAs. The `MahaRERA Agent` uses **async Playwright** to navigate the portal, intercepts the CAPTCHA image, sends it to an LLM for visual decoding, inputs the solution, and dynamically downloads the required legal and financial PDFs.

### Backend & Infrastructure
- **FastAPI:** High-performance, asynchronous REST API serving the pipeline.
- **Docker:** Fully containerized backend, ready for deployment to AWS ECS / AppRunner.
- **Python-docx:** Programmatic generation of the final, branded intelligence report.

---

## 🚀 Running the Project Locally

### Prerequisites
- Python 3.10+
- Docker (optional, for containerized execution)
- API Keys: Google Gemini & Groq

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/MahaFund-Brief.git
cd MahaFund-Brief
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

3. **Configure Environment:**
Copy the `.env.example` file and add your API keys:
```bash
cp .env.example .env
```

4. **Run the FastAPI Server:**
```bash
uvicorn src.server:app --reload --port 8000
```
The frontend will be available at `http://localhost:8000/`.

---

## 🐳 Docker Deployment (AWS ECS / AppRunner Ready)

To run the application in a production-ready container:

```bash
docker build -t mahafund-brief .
docker run -p 8000:8000 --env-file .env mahafund-brief
```

---

<div align="center">
  <p>Built with 💡 for the future of Real Estate Finance.</p>
</div>
