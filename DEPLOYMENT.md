# Deployment Guide

This guide describes how to deploy the **ChromaDB** vector database on Hugging Face Spaces (for free, high-performance cloud hosting) and connect it to your application deployed on **Render** (or another cloud provider).

---

## 1. Deploying ChromaDB on Hugging Face Spaces

Hugging Face Spaces allows you to deploy custom Docker containers with up to 16 GB of RAM for free.

### Step 1: Create a Space
1. Go to [Hugging Face Spaces](https://huggingface.co/spaces) and click **Create new Space**.
2. Give your Space a name (e.g., `ipo-chroma-db`).
3. Select **Docker** as the SDK.
4. Choose the **Blank** template.
5. Set Space visibility to **Public** (required to access it without authentication, or read below to secure it).

### Step 2: Create the Dockerfile
Hugging Face Spaces require containers to listen on **port 7860** to receive public HTTP requests.

Create a file named `Dockerfile` in the root of your newly created Hugging Face Space repository with the following lines:

```dockerfile
FROM chromadb/chroma:latest

# Force ChromaDB to run on port 7860 required by Hugging Face Spaces
ENV CHROMA_HOST_PORT=7860
ENV PORT=7860

EXPOSE 7860
```

*Note: This overrides Chroma's default internal port of 8000 and ensures the space deploys cleanly.*

### Step 3: Save and Build
1. Commit and save the file. Hugging Face will automatically trigger a build.
2. Once complete, your space will show a **Running** status.
3. Hugging Face will provide you with a public URL, which generally looks like:
   `https://<your-username>-<your-space-name>.hf.space`

---

## 2. Deploying the FastAPI Backend (on Render)

With ChromaDB running in the cloud, you can deploy the FastAPI backend to Render.

### Step 1: Create a Web Service
1. Go to [Render](https://render.com/) and create a new **Web Service**.
2. Connect your GitHub repository containing the `IPO-Analyst` code.

### Step 2: Configure Settings
* **Runtime:** `Python`
* **Build Command:** `pip install -r requirements.txt`
* **Start Command:** `uvicorn backend.api:app --host 0.0.0.0 --port $PORT`

### Step 3: Set Environment Variables
Add the following environment variables in Render's dashboard:

| Variable Name | Example Value | Description |
|---|---|---|
| `GROQ_API_KEY` | `gsk_...` | Your Groq API key |
| `CHROMA_HOST` | `https://username-space.hf.space` | The URL of your Hugging Face Space |
| `CHROMA_PORT` | `443` | Use 443 for HTTPS |
| `CHROMA_SSL` | `True` | Set to True for HTTPS |

*(Optional) If you secured your Space with a Token, set `CHROMA_AUTH_TOKEN=your_token`.*

---

## 3. Deploying the Streamlit Frontend (on Render)

Deploy the user interface as a separate Web Service on Render.

### Step 1: Create a Web Service
1. Create a second **Web Service** on Render pointing to the same repository.
2. Select `Python` as the runtime.

### Step 2: Configure Settings
* **Build Command:** `pip install -r requirements.txt`
* **Start Command:** `streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0`

### Step 3: Set Environment Variables
Add the following environment variable in the Render UI:

| Variable Name | Example Value | Description |
|---|---|---|
| `API_BASE` | `https://ipo-backend.onrender.com` | The public URL of your FastAPI backend service |

---

## 🔒 Securing ChromaDB (Optional)
If you do not want your ChromaDB database to be publicly accessible, you can make the Space **Private** and use Hugging Face token authentication, or implement API Token authorization. 

To use Token authorization on ChromaDB:
1. In your Hugging Face Space settings, set environment variables to configure token auth.
2. In your Render backend env settings, set:
   * `CHROMA_AUTH_TOKEN=your-secret-token`

---

## 4. Alternate: Connecting to Managed Chroma Cloud (trychroma.com)

If you signed up for an account on [trychroma.com](https://trychroma.com/) (Chroma Cloud), you do not need to host a database server on Hugging Face Spaces. 

### Step 1: Set Up Credentials in Chroma Cloud
1. Create a tenant and a database on the Chroma Cloud dashboard.
2. Generate an API Key.

### Step 2: Configure Render Backend Environment Variables
In your Render backend settings, delete the `CHROMA_HOST`, `CHROMA_PORT`, and `CHROMA_SSL` variables, and set these instead:

| Variable Name | Example Value | Description |
|---|---|---|
| `CHROMA_API_KEY` | `chroma-cloud-...` | Your Chroma Cloud API key |
| `CHROMA_TENANT` | `your-tenant-name` | Your Chroma Cloud tenant ID (defaults to `default_tenant`) |
| `CHROMA_DATABASE` | `your-database-name` | Your database name (defaults to `default_database`) |

*(Optional) If your database is hosted in a specific non-default region (like GCP europe-west1), also set `CHROMA_CLOUD_HOST` and `CHROMA_CLOUD_PORT` variables accordingly.*

