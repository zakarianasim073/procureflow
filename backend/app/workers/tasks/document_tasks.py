"""Document processing background tasks."""
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def process_document(self, file_path: str, document_type: str = "auto") -> dict:
    """Process uploaded document asynchronously."""
    try:
        from app.agents.document_agent import DocumentExtractionAgent
        agent = DocumentExtractionAgent()
        
        if document_type == "pdf" or document_type == "auto":
            result = agent.extract_from_pdf(file_path)
        elif document_type in ("excel", "xlsx"):
            result = agent.extract_from_excel(file_path)
        else:
            result = {"error": f"Unsupported document type: {document_type}"}
        
        return {"status": "completed", "result": result}
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def generate_document_preview(self, file_path: str) -> dict:
    """Generate a preview/summary of a document."""
    try:
        from app.agents.document_agent import DocumentExtractionAgent
        agent = DocumentExtractionAgent()
        classification = agent.classify_document(file_path)
        return {
            "status": "completed",
            "document_type": classification,
            "file_path": file_path,
        }
    except Exception as exc:
        raise self.retry(exc=exc)
