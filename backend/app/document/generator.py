import io
import re
import zipfile
from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor


class DocumentGenerator:
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def generate(self, title: str, document_type: str, request: str, assumptions: list[str], sections: list[dict[str, str]]) -> bytes:
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        style = doc.styles["Normal"]
        style.font.name = "Aptos"
        style.font.size = Pt(10)
        style.font.color.rgb = RGBColor(45, 55, 65)
        heading = doc.add_heading(title, 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
        subtitle = doc.add_paragraph(document_type)
        subtitle.runs[0].font.color.rgb = RGBColor(80, 105, 115)
        doc.add_paragraph(f"Prepared {date.today().strftime('%B %d, %Y')}")
        doc.add_paragraph(f"Request: {request}")
        if assumptions:
            doc.add_heading("Assumptions", level=1)
            for item in assumptions:
                doc.add_paragraph(item, style="List Bullet")
        for item in sections:
            doc.add_heading(item["heading"], level=1)
            for line in item["body"].splitlines():
                self._add_line(doc, line.strip())
        footer = section.footer.paragraphs[0]
        footer.text = "TaskPilot AI  |  Generated from user-provided requirements and stated assumptions"
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        stream = io.BytesIO()
        doc.save(stream)
        payload = stream.getvalue()
        if len(payload) < 1000 or not zipfile.is_zipfile(io.BytesIO(payload)):
            raise ValueError("Generated document failed DOCX integrity validation")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise ValueError("Generated document is missing its main content")
        return payload

    @staticmethod
    def _add_line(doc, line: str) -> None:
        if not line:
            return
        subheading = re.match(r"^#{1,6}\s+(.*)", line)
        if subheading:
            doc.add_heading(subheading.group(1).replace("**", ""), level=2)
            return
        bullet = re.match(r"^[-*\u2022]\s+(.*)", line)
        paragraph = doc.add_paragraph(style="List Bullet" if bullet else "Normal")
        for index, part in enumerate((bullet.group(1) if bullet else line).split("**")):
            if part:
                paragraph.add_run(part).bold = index % 2 == 1
