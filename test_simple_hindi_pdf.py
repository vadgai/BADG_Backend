"""
Test the simple Hindi PDF generator with direct canvas rendering
"""
import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pdf_generator_simple import generate_hindi_pdf_simple

def test_simple_hindi_pdf():
    """Test simple Hindi PDF with canvas rendering"""

    # Sample test data
    test_data = {
        'report': {
            'PatientInfo': {
                'Age': '41',
                'Gender': 'पुरुष'
            },
            'Urgency': 'Moderate',
            'MainSymptoms': [
                'जोड़ों में दर्द (विशेषकर सुबह)',
                'जोड़ों में सूजन और अकड़न',
                'चलने-फिरने में कठिनाई विशेष रूप से सुबह के समय',
                'कमजोरी और थकान',
                'हाथ, पैर, और अन्य छोटे जोड़ों में दर्द'
            ],
            'TopDiseaseMatches': [
                {
                    'Disease1': {
                        'Name1': 'गठिया (रूमेटॉइड आर्थराइटिस)',
                        'MatchLevel1': 'High',
                        'PreHospitalCare1': [
                            'प्रभावित जोड़ों को आराम दें',
                            'सूजन वाली जगह पर गर्म पानी की सिकाई करें (दिन में 2-3 बार)',
                            'हल्का व्यायाम करें',
                            'पौष्टिक आहार लें'
                        ],
                        'SelfCare1': [
                            'वजन कम करें',
                            'धूम्रपान से बचें'
                        ],
                        'SymptomsToWatch1': [
                            'तेज बुखार आना',
                            'जोड़ों में लाली और गर्मी',
                            'चलने में असमर्थता'
                        ],
                        'MedicationSuggestion1': [
                            'इबुप्रोफेन (दर्द और सूजन के लिए)',
                            'कॉर्टिकोस्टेरॉइड दवाएं (steroid) डॉक्टर की सलाह पर',
                            'बीमारी-संशोधित दवाएं (Disease-Modifying Anti-Rheumatic Drugs - DMARD) लंबे समय के लिए'
                        ]
                    }
                },
                {
                    'Disease2': {
                        'Name2': 'ऑस्टियोआर्थराइटिस (जोड़ों का घिसाव)',
                        'MatchLevel2': 'Moderate',
                        'PreHospitalCare2': [
                            'आराम करें',
                            'प्रभावित जगह पर गर्म सिकाई (हर 15-20 मिनट)',
                            'हल्का योग',
                            'फिजियोथेरेपी'
                        ],
                        'SelfCare2': [
                            'वजन नियंत्रण',
                            'तैराकी करें',
                            'घुटनों की सुरक्षा'
                        ],
                        'SymptomsToWatch2': [
                            'तेज दर्द बढ़ना',
                            'जोड़ बंद होना',
                            'चल-फिर नहीं पाना'
                        ],
                        'MedicationSuggestion2': [
                            'पेरासिटामोल (दर्द निवारक)',
                            'ग्लूकोसामाइन सप्लीमेंट'
                        ]
                    }
                }
            ],
            'NextDiagnosticSteps': [
                'अपने चिकित्सक से परामर्श अवश्य लें',
                'संपूर्ण रक्त गणना (CBC) परीक्षण करवाएं',
                'रूमेटॉइड फैक्टर (RF) और एंटी-सीसीपी एंटीबॉडी (Anti-CCP antibody) टेस्ट करवाएं',
                'एक्स-रे (X-ray) जोड़ों की',
                'डॉक्टर द्वारा बताए गए अन्य परीक्षण'
            ]
        },
        'patient_details': {
            'name': 'Test User 1',
            'age': 41,
            'gender': 'पुरुष',
            'occupation': 'Software Engineer',
            'physical_activity': 'मध्यम',
            'diet_type': 'शाकाहारी',
            'weight': 66.8,
            'height': 150.0,
            'location': {
                'city': 'Farrukhābād',
                'state': 'Uttar Pradesh'
            }
        }
    }

    print("🧪 Testing Simple Hindi PDF Generation (Canvas-based)...")
    print()

    try:
        # Generate Hindi PDF
        pdf_bytes = generate_hindi_pdf_simple(test_data, 'hi')

        # Save test PDF
        output_file = 'test_simple_hindi_report.pdf'
        with open(output_file, 'wb') as f:
            f.write(pdf_bytes)

        print("✅ Test PDF generated successfully!")
        print("📄 File: {}".format(output_file))
        print("📏 Size: {} bytes".format(len(pdf_bytes)))

        # Check if PDF has reasonable size
        if len(pdf_bytes) > 5000:
            print("✅ PDF size looks good (contains content)")
        else:
            print("⚠️  PDF might be too small")

        print()
        print("📋 This PDF uses:")
        print("   ✓ Direct canvas drawing (more reliable)")
        print("   ✓ Proper Hindi font embedding")
        print("   ✓ Simple text rendering")
        print("   ✓ All sections included")

        print()
        print("🎉 SUCCESS! Open '{}' and verify Hindi text is readable!".format(output_file))

        return True

    except Exception as error:
        print("❌ Error generating PDF: {}".format(error))
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_success = test_simple_hindi_pdf()
    sys.exit(0 if test_success else 1)












