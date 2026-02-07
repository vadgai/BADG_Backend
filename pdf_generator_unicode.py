"""
Unicode PDF Generator using ReportLab
Properly handles Hindi/Devanagari and other Indic scripts
"""

import os
import unicodedata
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

# Font paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, 'fonts')
DEVANAGARI_FONT = os.path.join(FONT_DIR, 'NotoSansDevanagari-Regular.ttf')

# Register Unicode font
def register_unicode_fonts():
    """Register Devanagari font for Hindi text"""
    try:
        if os.path.exists(DEVANAGARI_FONT):
            pdfmetrics.registerFont(TTFont('NotoDev', DEVANAGARI_FONT))
            print(f"✅ Registered font: {DEVANAGARI_FONT}")
            return True
        else:
            print(f"⚠️ Font not found: {DEVANAGARI_FONT}")
            return False
    except Exception as e:
        print(f"❌ Font registration error: {e}")
        return False

# Normalize Unicode text
def normalize_text(text):
    """Normalize Unicode to NFC form to avoid split graphemes"""
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text))

def generate_hindi_pdf(report_data, language='hi'):
    """
    Generate PDF with proper Unicode support for Hindi
    Same structure as the preview report
    
    Args:
        report_data: Dict with report information
        language: Language code (hi, ta, te, etc.)
    
    Returns:
        BytesIO: PDF file bytes
    """
    
    # Register fonts
    font_registered = register_unicode_fonts()
    font_name = 'NotoDev' if font_registered and language != 'en' else 'Helvetica'
    
    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    
    # Build story (content)
    story = []
    
    # Create styles with Unicode font
    styles = getSampleStyleSheet()
    
    # Custom styles for Hindi
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName=font_name,
        fontSize=18,
        textColor=colors.HexColor('#1A3C73'),
        spaceAfter=8,
        alignment=TA_CENTER,
        leading=22
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['BodyText'],
        fontName=font_name,
        fontSize=10,
        textColor=colors.HexColor('#333333'),
        spaceAfter=10,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName=font_name,
        fontSize=12,
        textColor=colors.HexColor('#1A3C73'),
        spaceAfter=5,
        spaceBefore=8,
        leading=15
    )
    
    subheading_style = ParagraphStyle(
        'CustomSubheading',
        parent=styles['Heading3'],
        fontName=font_name,
        fontSize=10,
        textColor=colors.HexColor('#1A3C73'),
        spaceAfter=3,
        spaceBefore=5,
        leading=13
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontName=font_name,
        fontSize=9,
        spaceAfter=4,
        leading=12
    )
    
    bullet_style = ParagraphStyle(
        'CustomBullet',
        parent=styles['BodyText'],
        fontName=font_name,
        fontSize=9,
        leftIndent=15,
        bulletIndent=5,
        spaceAfter=3,
        leading=12
    )
    
    label_style = ParagraphStyle(
        'CustomLabel',
        parent=styles['BodyText'],
        fontName=font_name,
        fontSize=8,
        textColor=colors.HexColor('#666666'),
        spaceAfter=2
    )
    
    # Extract report data
    report = report_data.get('report', {})
    patient_info = report.get('PatientInfo', {})
    patient_details = report_data.get('patient_details', {})
    
    # ============= HEADER =============
    title = normalize_text("VADG बुद्धिमान निदान रिपोर्ट" if language == 'hi' else "VADG Intelligent Diagnosis Report")
    story.append(Paragraph(title, title_style))
    
    subtitle = normalize_text("आपकी व्यक्तिगत AI जनित स्वास्थ्य रिपोर्ट समीक्षा के लिए तैयार है।" if language == 'hi' else "Your personalized AI-generated health report is ready for review.")
    story.append(Paragraph(subtitle, subtitle_style))
    
    # Severity Index
    urgency = report.get('Urgency', 'Moderate')
    if language == 'hi':
        urgency_map = {
            'High': 'उच्च',
            'Moderate': 'मध्यम',
            'Low': 'कम',
            'Critical': 'गंभीर',
            'Routine': 'सामान्य',
            'Emergency': 'आपातकालीन'
        }
        urgency_text = urgency_map.get(urgency, urgency)
        severity_text = f"गंभीरता सूचकांक: {urgency_text}"
    else:
        severity_text = f"Severity Index: {urgency}"
    
    story.append(Paragraph(normalize_text(severity_text), body_style))
    story.append(Spacer(1, 5*mm))
    
    # ============= PATIENT PROFILE =============
    profile_heading = normalize_text("मरीज की जानकारी" if language == 'hi' else "Patient Profile")
    story.append(Paragraph(profile_heading, heading_style))
    
    # Build patient info grid with all fields
    patient_fields = []
    
    # Name
    name_label = "नाम:" if language == 'hi' else "Name:"
    patient_fields.append([
        normalize_text(name_label),
        normalize_text(str(patient_details.get('name', 'N/A')))
    ])
    
    # Age and Gender
    age_label = "उम्र:" if language == 'hi' else "Age:"
    gender_label = "लिंग:" if language == 'hi' else "Gender:"
    patient_fields.append([
        normalize_text(age_label),
        normalize_text(f"{patient_info.get('Age', 'N/A')} वर्ष" if language == 'hi' else f"{patient_info.get('Age', 'N/A')} years")
    ])
    patient_fields.append([
        normalize_text(gender_label),
        normalize_text(str(patient_info.get('Gender', 'N/A')))
    ])
    
    # Weight and Height
    if patient_details.get('weight') and patient_details.get('height'):
        measures_label = "शारीरिक माप:" if language == 'hi' else "Physical Measurements:"
        patient_fields.append([
            normalize_text(measures_label),
            normalize_text(f"{patient_details.get('weight')} kg, {patient_details.get('height')} cm")
        ])
    
    
    # Create patient info table
    patient_table = Table(patient_fields, colWidths=[45*mm, 125*mm])
    patient_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F9F9F9')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E0E0E0')),
    ]))
    story.append(patient_table)
    story.append(Spacer(1, 5*mm))
    
    # ============= PRIMARY SYMPTOMS =============
    symptoms = report.get('MainSymptoms', [])
    if symptoms:
        symptoms_heading = normalize_text("मुख्य स्वास्थ्य लक्षण" if language == 'hi' else "Primary Health Symptoms")
        story.append(Paragraph(symptoms_heading, heading_style))
        
        for symptom in symptoms:
            symptom_text = normalize_text(f"• {symptom}")
            story.append(Paragraph(symptom_text, bullet_style))
        story.append(Spacer(1, 5*mm))
    
    # ============= PROBABLE DIAGNOSES =============
    diagnoses_heading = normalize_text("संभावित निदान" if language == 'hi' else "Probable Diagnoses Based on VADG AI Analysis")
    story.append(Paragraph(diagnoses_heading, heading_style))
    
    diseases = report.get('TopDiseaseMatches', [])
    for idx, disease_obj in enumerate(diseases[:2]):
        disease_key = list(disease_obj.keys())[0]
        disease = disease_obj[disease_key]
        num = disease_key.replace('Disease', '')
        
        # Disease name and match level
        disease_name = normalize_text(disease.get(f'Name{num}', 'N/A'))
        match_level = disease.get(f'MatchLevel{num}', 'N/A')
        
        if language == 'hi':
            match_map = {'High': 'उच्च मिलान', 'Moderate': 'मध्यम मिलान', 'Low': 'कम मिलान'}
            match_text = match_map.get(match_level, match_level)
        else:
            match_text = f"{match_level} Match"
        
        disease_title = normalize_text(f"{idx + 1}. {disease_name} [{match_text}]")
        story.append(Paragraph(disease_title, subheading_style))
        story.append(Spacer(1, 2*mm))
        
        # HOME CARE / SELF CARE
        home_care_label = normalize_text("घरेलू देखभाल / स्व-देखभाल:" if language == 'hi' else "Home Care / Self Care:")
        story.append(Paragraph(home_care_label, body_style))
        
        care_items = disease.get(f'PreHospitalCare{num}', []) + disease.get(f'SelfCare{num}', [])
        for care in care_items:
            care_text = normalize_text(f"• {care}")
            story.append(Paragraph(care_text, bullet_style))
        
        story.append(Spacer(1, 2*mm))
        
        # RED FLAG SYMPTOMS
        red_flags = disease.get(f'SymptomsToWatch{num}', [])
        if red_flags:
            red_flag_label = normalize_text("खतरे के संकेत (तुरंत चिकित्सा सहायता लें):" if language == 'hi' else "Red Flag Symptoms (Seek Urgent Medical Help):")
            story.append(Paragraph(red_flag_label, body_style))
            
            for flag in red_flags:
                flag_text = normalize_text(f"• {flag}")
                story.append(Paragraph(flag_text, bullet_style))
            
            story.append(Spacer(1, 2*mm))
        
        # MEDICATION SUGGESTIONS
        medications = disease.get(f'MedicationSuggestion{num}', [])
        if medications:
            med_label = normalize_text("दवा के सुझाव (केवल शैक्षिक उद्देश्य के लिए):" if language == 'hi' else "Medication Suggestions (For Educational Purposes Only):")
            story.append(Paragraph(med_label, body_style))
            
            for med in medications:
                med_text = normalize_text(f"• {med}")
                story.append(Paragraph(med_text, bullet_style))
        
        story.append(Spacer(1, 4*mm))
    
    # ============= NEXT DIAGNOSTIC STEPS =============
    if report.get('NextDiagnosticSteps'):
        next_steps_heading = normalize_text("अगले निदान चरण" if language == 'hi' else "Next Diagnostic Steps")
        story.append(Paragraph(next_steps_heading, heading_style))
        
        for step in report['NextDiagnosticSteps']:
            step_text = normalize_text(f"• {step}")
            story.append(Paragraph(step_text, bullet_style))
        
        story.append(Spacer(1, 5*mm))
    
    # ============= FOOTER / DISCLAIMER =============
    disclaimer_heading = normalize_text("महत्वपूर्ण अस्वीकरण:" if language == 'hi' else "Important Disclaimer:")
    story.append(Paragraph(disclaimer_heading, heading_style))
    
    disclaimer_text = normalize_text(
        "यह रिपोर्ट केवल शैक्षिक और सूचनात्मक उद्देश्यों के लिए AI द्वारा उत्पन्न की गई है। यह पेशेवर चिकित्सा सलाह, निदान या उपचार का विकल्प नहीं है। कृपया किसी योग्य स्वास्थ्य सेवा प्रदाता से परामर्श करें।" 
        if language == 'hi' else 
        "This report is AI-generated for educational and informational purposes only. It is not a substitute for professional medical advice, diagnosis, or treatment. Please consult a qualified healthcare provider."
    )
    story.append(Paragraph(disclaimer_text, body_style))
    
    # Build PDF
    doc.build(story)
    
    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes

def test_hindi_pdf():
    """Test function to verify Hindi PDF generation"""
    test_data = {
        'report': {
            'PatientInfo': {
                'Age': '30',
                'Gender': 'पुरुष'
            },
            'MainSymptoms': [
                'बुखार',
                'खांसी',
                'सिरदर्द'
            ],
            'TopDiseaseMatches': [
                {
                    'Disease1': {
                        'Name1': 'सामान्य सर्दी',
                        'MatchLevel1': 'High',
                        'PreHospitalCare1': ['आराम करें', 'पानी पिएं'],
                        'SelfCare1': []
                    }
                }
            ],
            'NextDiagnosticSteps': [
                'डॉक्टर से मिलें',
                'रक्त परीक्षण करवाएं'
            ]
        },
        'patient_details': {
            'name': 'टेस्ट रोगी'
        }
    }
    
    pdf_bytes = generate_hindi_pdf(test_data, 'hi')
    
    # Save test PDF
    with open('test_hindi_report.pdf', 'wb') as f:
        f.write(pdf_bytes)
    
    print("✅ Test PDF generated: test_hindi_report.pdf")
    print(f"📄 Size: {len(pdf_bytes)} bytes")
    
    # Verify text contains Hindi
    if len(pdf_bytes) > 1000:
        print("✅ PDF size looks good")
    else:
        print("⚠️ PDF might be too small")

if __name__ == '__main__':
    test_hindi_pdf()


