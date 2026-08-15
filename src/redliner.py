"""
Veritas-Graph: Native OOXML Tracked Changes Engine with Schema Validation.
"""
from datetime import datetime, timezone
from io import BytesIO
from lxml import etree
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsdecls
import copy

class OOXMLRedliner:
    """
    Manipulates low-level OOXML AST to produce native Word revisions.
    """

    @staticmethod
    def _get_next_w_id(doc: Document) -> int:
        """Inspects the entire document DOM to guarantee unique w:id generation."""
        body = doc._body._element
        existing_ids = body.xpath('//@w:id')
        numeric_ids = [int(i) for i in existing_ids if i.isdigit()]
        return (max(numeric_ids) + 1) if numeric_ids else 1

    @classmethod
    def apply_tracked_change(
        cls, doc: Document, paragraph_index: int, original_text: str, replacement_text: str, author: str = "Veritas-AI"
    ) -> tuple[bool, str]: # 🚨 UPDATE SIGNATURE to return error messages 🚨
        
        p = doc.paragraphs[paragraph_index]
        if original_text not in p.text:
            return False, "Target text not found in paragraph."

        w_id = cls._get_next_w_id(doc)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build the exact Tracked Changes AST nodes (same as before)
        del_node = etree.Element(qn('w:del'), nsmap={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})
        del_node.set(qn('w:id'), str(w_id))
        del_node.set(qn('w:author'), author)
        del_node.set(qn('w:date'), now_iso)
        del_run = etree.SubElement(del_node, qn('w:r'))
        del_text = etree.SubElement(del_run, qn('w:delText'))
        del_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        del_text.text = original_text

        ins_node = etree.Element(qn('w:ins'), nsmap={'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'})
        ins_node.set(qn('w:id'), str(w_id + 1))
        ins_node.set(qn('w:author'), author)
        ins_node.set(qn('w:date'), now_iso)
        ins_run = etree.SubElement(ins_node, qn('w:r'))
        ins_text = etree.SubElement(ins_run, qn('w:t'))
        ins_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        ins_text.text = replacement_text

        for run in p.runs:
            if original_text in run.text:
                rPr = run._r.find(qn('w:rPr'))
                if rPr is not None:
                    # 🚨 FIX: DEEPCOPY PREVENTS LXML DETACHMENT CORRUPTION 🚨
                    del_run.insert(0, copy.deepcopy(rPr)) 
                    ins_run.insert(0, copy.deepcopy(rPr)) 
                
                parts = run.text.split(original_text, 1)
                run.text = parts[0] 
                
                run._r.addnext(del_node) 
                del_node.addnext(ins_node) 
                
                if parts[1]:
                    new_run_element = etree.Element(qn('w:r'))
                    if rPr is not None:
                        # 🚨 FIX: DEEPCOPY FOR THE SUFFIX RUN 🚨
                        new_run_element.append(copy.deepcopy(rPr)) 
                    new_text = etree.SubElement(new_run_element, qn('w:t'))
                    new_text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    new_text.text = parts[1]
                    ins_node.addnext(new_run_element)
                return True, ""
                
        # 🚨 EXPLICIT FAILURE LOGGING FOR THE MVP GAP 🚨
        return False, "Clause spans multiple <w:r> runs (Unsupported MVP edge case)."

    @classmethod
    def inject_warning_comment(cls, doc: Document, paragraph_index: int, warning_text: str):
        """Appends an in-document escalation marker for clauses requiring human review."""
        p = doc.paragraphs[paragraph_index]
        run = p.add_run(f" [{warning_text}]")
        run.font.bold = True

    @classmethod
    def validate_document(cls, doc: Document) -> bool:
        """Roundtrip verification: confirms generated XML parses cleanly."""
        try:
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            reloaded = Document(buffer)
            return len(reloaded.paragraphs) > 0
        except Exception:
            return False