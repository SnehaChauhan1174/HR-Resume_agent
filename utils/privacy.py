import re

def mask_pii(text:str)->str:
    """masking emails and phones before writing to any log file."""
    text = re.sub(r'\b[\w._%+-]+@[\w.-]\.[a-zA-Z]{2,}\b','[EMAIL]',text)
    text = re.sub(r'\b(\+91[\s-]?)?[6-9]\d{9}\b','[PHONE]',text)
    return text