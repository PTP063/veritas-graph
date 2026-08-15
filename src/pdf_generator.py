from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def generate_mock_pdf(output_path: str) -> None:
    c = canvas.Canvas(output_path, pagesize=letter)

    # Page 1
    c.drawString(100, 700, "Corporate Contract")
    c.drawString(100, 680, "This is page 1 of the mock contract.")
    c.showPage()

    # Page 2
    c.drawString(100, 700, "Terms and Conditions")
    c.drawString(100, 680, "In the event of a Change of Control, the following terms apply.")
    c.showPage()

    c.save()
