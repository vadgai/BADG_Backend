"""
Simple PDF Generator with proper Hindi Unicode support
Uses canvas direct drawing for reliable Hindi text rendering
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

# Font paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, 'fonts')
DEVANAGARI_FONT = os.path.join(FONT_DIR, 'NotoSansDevanagari-Regular.ttf')

# Page settings
PAGE_WIDTH = A4[0]
PAGE_HEIGHT = A4[1]
MARGIN_LEFT = 15 * mm
MARGIN_RIGHT = 15 * mm
MARGIN_TOP = 15 * mm
MARGIN_BOTTOM = 15 * mm
CONTENT_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

def normalize_text(text):
    """Normalize Unicode to NFC form"""
    if not text:
        return ""
    return unicodedata.normalize('NFC', str(text))

def register_font():
    """Register Hindi font"""
    try:
        if os.path.exists(DEVANAGARI_FONT):
            pdfmetrics.registerFont(TTFont('HindiFont', DEVANAGARI_FONT))
            print(f"✅ Font registered: {DEVANAGARI_FONT}")
            return True
        else:
            print(f"⚠️  Font not found: {DEVANAGARI_FONT}")
            return False
    except Exception as e:
        print(f"❌ Font error: {e}")
        return False

def draw_text(c, x, y, text, font='HindiFont', size=10, color_hex='#000000'):
    """Draw text with proper font"""
    c.setFont(font, size)
    c.setFillColor(colors.HexColor(color_hex))
    c.drawString(x, y, normalize_text(text))
    return y - size - 3

def draw_bullet_text(c, x, y, text, font='HindiFont', size=9):
    """Draw bullet point text"""
    c.setFont(font, size)
    c.setFillColor(colors.black)
    c.drawString(x, y, "•")
    
    # Word wrap for long text
    words = normalize_text(text).split()
    line = ""
    line_y = y
    max_width = CONTENT_WIDTH - (x - MARGIN_LEFT) - 10
    
    for word in words:
        test_line = line + " " + word if line else word
        if c.stringWidth(test_line, font, size) < max_width:
            line = test_line
        else:
            if line:
                c.drawString(x + 10, line_y, line)
                line_y -= size + 3
            line = word
    
    if line:
        c.drawString(x + 10, line_y, line)
        line_y -= size + 3
    
    return line_y - 3

def generate_hindi_pdf_simple(report_data, language='hi'):
    """
    Generate simple Hindi PDF with direct canvas drawing
    """
    
    # Register font
    font_ok = register_font()
    font_name = 'HindiFont' if font_ok and language == 'hi' else 'Helvetica'
    
    # Create buffer
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # Extract data
    report = report_data.get('report', {})
    patient_info = report.get('PatientInfo', {})
    patient_details = report_data.get('patient_details', {})
    
    # Starting position
    y = PAGE_HEIGHT - MARGIN_TOP
    
    # ============= HEADER =============
    c.setFont(font_name, 18)
    c.setFillColor(colors.HexColor('#1A3C73'))
    title = "VADG बुद्धिमान निदान रिपोर्ट" if language == 'hi' else "VADG Intelligent Diagnosis Report"
    title_width = c.stringWidth(normalize_text(title), font_name, 18)
    c.drawString((PAGE_WIDTH - title_width) / 2, y, normalize_text(title))
    y -= 25
    
    c.setFont(font_name, 10)
    c.setFillColor(colors.HexColor('#333333'))
    subtitle = "आपकी व्यक्तिगत AI जनित स्वास्थ्य रिपोर्ट समीक्षा के लिए तैयार है।" if language == 'hi' else "Your personalized AI-generated health report is ready for review."
    subtitle_width = c.stringWidth(normalize_text(subtitle), font_name, 10)
    c.drawString((PAGE_WIDTH - subtitle_width) / 2, y, normalize_text(subtitle))
    y -= 20
    
    # Severity
    urgency = report.get('Urgency', 'Moderate')
    if language == 'hi':
        urgency_map = {'High': 'उच्च', 'Moderate': 'मध्यम', 'Low': 'कम', 'Critical': 'गंभीर'}
        urgency_text = urgency_map.get(urgency, urgency)
        severity_text = f"गंभीरता सूचकांक: {urgency_text}"
    else:
        severity_text = f"Severity Index: {urgency}"
    
    c.setFont(font_name, 9)
    c.setFillColor(colors.black)
    c.drawString(MARGIN_LEFT, y, normalize_text(severity_text))
    y -= 20
    
    # ============= PATIENT PROFILE =============
    c.setFont(font_name, 12)
    c.setFillColor(colors.HexColor('#1A3C73'))
    heading = "मरीज की जानकारी" if language == 'hi' else "Patient Profile"
    c.drawString(MARGIN_LEFT, y, normalize_text(heading))
    y -= 18
    
    c.setFont(font_name, 9)
    c.setFillColor(colors.black)
    
    # Patient info
    info_lines = []
    if language == 'hi':
        info_lines.append(f"नाम: {patient_details.get('name', 'N/A')}")
        info_lines.append(f"उम्र: {patient_info.get('Age', 'N/A')} वर्ष")
        info_lines.append(f"लिंग: {patient_info.get('Gender', 'N/A')}")
        if patient_details.get('weight') and patient_details.get('height'):
            info_lines.append(f"शारीरिक माप: {patient_details.get('weight')} kg, {patient_details.get('height')} cm")
    else:
        info_lines.append(f"Name: {patient_details.get('name', 'N/A')}")
        info_lines.append(f"Age: {patient_info.get('Age', 'N/A')} years")
        info_lines.append(f"Gender: {patient_info.get('Gender', 'N/A')}")
        if patient_details.get('weight') and patient_details.get('height'):
            info_lines.append(f"Physical Measurements: {patient_details.get('weight')} kg, {patient_details.get('height')} cm")
    
    for line in info_lines:
        c.drawString(MARGIN_LEFT + 5, y, normalize_text(line))
        y -= 12
    
    y -= 10
    
    # Check if we need a new page
    if y < 200:
        c.showPage()
        y = PAGE_HEIGHT - MARGIN_TOP
    
    # ============= SYMPTOMS =============
    symptoms = report.get('MainSymptoms', [])
    if symptoms:
        c.setFont(font_name, 12)
        c.setFillColor(colors.HexColor('#1A3C73'))
        heading = "मुख्य स्वास्थ्य लक्षण" if language == 'hi' else "Primary Health Symptoms"
        c.drawString(MARGIN_LEFT, y, normalize_text(heading))
        y -= 18
        
        for symptom in symptoms:
            y = draw_bullet_text(c, MARGIN_LEFT + 5, y, str(symptom), font_name, 9)
        
        y -= 10
    
    # Check page
    if y < 250:
        c.showPage()
        y = PAGE_HEIGHT - MARGIN_TOP
    
    # ============= DIAGNOSES =============
    c.setFont(font_name, 12)
    c.setFillColor(colors.HexColor('#1A3C73'))
    heading = "संभावित निदान" if language == 'hi' else "Probable Diagnoses"
    c.drawString(MARGIN_LEFT, y, normalize_text(heading))
    y -= 18
    
    diseases = report.get('TopDiseaseMatches', [])
    for idx, disease_obj in enumerate(diseases[:2]):
        if y < 300:
            c.showPage()
            y = PAGE_HEIGHT - MARGIN_TOP
        
        disease_key = list(disease_obj.keys())[0]
        disease = disease_obj[disease_key]
        num = disease_key.replace('Disease', '')
        
        # Disease name
        disease_name = disease.get(f'Name{num}', 'N/A')
        match_level = disease.get(f'MatchLevel{num}', 'N/A')
        
        if language == 'hi':
            match_map = {'High': 'उच्च मिलान', 'Moderate': 'मध्यम मिलान', 'Low': 'कम मिलान'}
            match_text = match_map.get(match_level, match_level)
        else:
            match_text = f"{match_level} Match"
        
        c.setFont(font_name, 11)
        c.setFillColor(colors.HexColor('#1A3C73'))
        c.drawString(MARGIN_LEFT, y, normalize_text(f"{idx + 1}. {disease_name} [{match_text}]"))
        y -= 15
        
        # Home Care
        c.setFont(font_name, 10)
        c.setFillColor(colors.black)
        label = "घरेलू देखभाल / स्व-देखभाल:" if language == 'hi' else "Home Care / Self Care:"
        c.drawString(MARGIN_LEFT + 5, y, normalize_text(label))
        y -= 12
        
        care_items = disease.get(f'PreHospitalCare{num}', []) + disease.get(f'SelfCare{num}', [])
        for care in care_items:
            y = draw_bullet_text(c, MARGIN_LEFT + 10, y, str(care), font_name, 9)
            if y < 100:
                c.showPage()
                y = PAGE_HEIGHT - MARGIN_TOP
        
        y -= 5
        
        # Red Flags
        red_flags = disease.get(f'SymptomsToWatch{num}', [])
        if red_flags:
            c.setFont(font_name, 10)
            c.setFillColor(colors.black)
            label = "खतरे के संकेत:" if language == 'hi' else "Red Flag Symptoms:"
            c.drawString(MARGIN_LEFT + 5, y, normalize_text(label))
            y -= 12
            
            for flag in red_flags:
                y = draw_bullet_text(c, MARGIN_LEFT + 10, y, str(flag), font_name, 9)
                if y < 100:
                    c.showPage()
                    y = PAGE_HEIGHT - MARGIN_TOP
            
            y -= 5
        
        # Medications
        medications = disease.get(f'MedicationSuggestion{num}', [])
        if medications:
            c.setFont(font_name, 10)
            c.setFillColor(colors.black)
            label = "दवा के सुझाव:" if language == 'hi' else "Medication Suggestions:"
            c.drawString(MARGIN_LEFT + 5, y, normalize_text(label))
            y -= 12
            
            for med in medications:
                y = draw_bullet_text(c, MARGIN_LEFT + 10, y, str(med), font_name, 9)
                if y < 100:
                    c.showPage()
                    y = PAGE_HEIGHT - MARGIN_TOP
        
        y -= 15
    
    # ============= NEXT STEPS =============
    if report.get('NextDiagnosticSteps'):
        if y < 150:
            c.showPage()
            y = PAGE_HEIGHT - MARGIN_TOP
        
        c.setFont(font_name, 12)
        c.setFillColor(colors.HexColor('#1A3C73'))
        heading = "अगले निदान चरण" if language == 'hi' else "Next Diagnostic Steps"
        c.drawString(MARGIN_LEFT, y, normalize_text(heading))
        y -= 18
        
        for step in report['NextDiagnosticSteps']:
            y = draw_bullet_text(c, MARGIN_LEFT + 5, y, str(step), font_name, 9)
            if y < 100:
                c.showPage()
                y = PAGE_HEIGHT - MARGIN_TOP
        
        y -= 10
    
    # ============= DISCLAIMER =============
    if y < 100:
        c.showPage()
        y = PAGE_HEIGHT - MARGIN_TOP
    
    c.setFont(font_name, 11)
    c.setFillColor(colors.HexColor('#1A3C73'))
    heading = "महत्वपूर्ण अस्वीकरण:" if language == 'hi' else "Important Disclaimer:"
    c.drawString(MARGIN_LEFT, y, normalize_text(heading))
    y -= 15
    
    c.setFont(font_name, 8)
    c.setFillColor(colors.black)
    disclaimer = "यह रिपोर्ट केवल शैक्षिक और सूचनात्मक उद्देश्यों के लिए AI द्वारा उत्पन्न की गई है। यह पेशेवर चिकित्सा सलाह, निदान या उपचार का विकल्प नहीं है। कृपया किसी योग्य स्वास्थ्य सेवा प्रदाता से परामर्श करें।" if language == 'hi' else "This report is AI-generated for educational purposes only. It is not a substitute for professional medical advice."
    
    # Word wrap disclaimer
    words = normalize_text(disclaimer).split()
    line = ""
    for word in words:
        test_line = line + " " + word if line else word
        if c.stringWidth(test_line, font_name, 8) < CONTENT_WIDTH - 10:
            line = test_line
        else:
            c.drawString(MARGIN_LEFT + 5, y, line)
            y -= 10
            line = word
    if line:
        c.drawString(MARGIN_LEFT + 5, y, line)
    
    # Save
    c.save()
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes












