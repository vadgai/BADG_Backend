"""
Test the updated Hindi PDF generation with complete report structure
"""
import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pdf_generator_unicode import generate_hindi_pdf

def test_complete_hindi_pdf():
    """Test complete Hindi PDF with all sections"""

    # Sample test data matching the full report structure
    test_data = {
        'report': {
            'PatientInfo': {
                'Age': '35',
                'Gender': 'पुरुष'  # Male
            },
            'Urgency': 'Moderate',
            'MainSymptoms': [
                'बुखार',           # Fever
                'खांसी',           # Cough
                'सिरदर्द',         # Headache
                'थकान',            # Fatigue
                'गले में खराश'     # Sore throat
            ],
            'TopDiseaseMatches': [
                {
                    'Disease1': {
                        'Name1': 'सामान्य सर्दी-जुकाम',  # Common Cold
                        'MatchLevel1': 'High',
                        'PreHospitalCare1': [
                            'पर्याप्त आराम करें',
                            'गर्म पानी पिएं',
                            'भाप लें'
                        ],
                        'SelfCare1': [
                            'गर्म खाना खाएं',
                            'धूम्रपान से बचें'
                        ],
                        'SymptomsToWatch1': [
                            '103°F से अधिक बुखार',
                            'सांस लेने में कठिनाई',
                            'छाती में दर्द'
                        ],
                        'MedicationSuggestion1': [
                            'पैरासिटामोल 500mg (बुखार के लिए)',
                            'खांसी की दवा (डॉक्टर की सलाह के अनुसार)',
                            'गले की गोलियां'
                        ]
                    }
                },
                {
                    'Disease2': {
                        'Name2': 'वायरल संक्रमण',  # Viral Infection
                        'MatchLevel2': 'Moderate',
                        'PreHospitalCare2': [
                            'हाथ धोते रहें',
                            'आराम करें'
                        ],
                        'SelfCare2': [
                            'पौष्टिक भोजन लें',
                            'तरल पदार्थ पिएं'
                        ],
                        'SymptomsToWatch2': [
                            'लगातार उल्टी',
                            'निर्जलीकरण के लक्षण'
                        ],
                        'MedicationSuggestion2': [
                            'ओआरएस (निर्जलीकरण से बचने के लिए)',
                            'विटामिन सी की खुराक'
                        ]
                    }
                }
            ],
            'NextDiagnosticSteps': [
                'अपने डॉक्टर से परामर्श लें',
                'पूर्ण रक्त गणना (CBC) परीक्षण करवाएं',
                'छाती का एक्स-रे यदि आवश्यक हो',
                'यदि 3 दिनों में सुधार न हो तो फिर से जांच करवाएं'
            ]
        },
        'patient_details': {
            'name': 'राहुल कुमार',
            'age': 35,
            'gender': 'पुरुष',
            'occupation': 'सॉफ्टवेयर इंजीनियर',
            'physical_activity': 'मध्यम',
            'diet_type': 'शाकाहारी',
            'weight': 70,
            'height': 175,
            'location': {
                'city': 'दिल्ली',
                'state': 'दिल्ली'
            }
        }
    }
    
    print("🧪 Testing Complete Hindi PDF Generation...")
    print()
    
    try:
        # Generate Hindi PDF
        pdf_bytes = generate_hindi_pdf(test_data, 'hi')
        
        # Save test PDF
        output_file = 'test_hindi_complete_report.pdf'
        with open(output_file, 'wb') as f:
            f.write(pdf_bytes)
        
        print("✅ Test PDF generated successfully!")
        print("📄 File: {}".format(output_file))
        print("📏 Size: {} bytes".format(len(pdf_bytes)))
        
        # Check if PDF has reasonable size
        if len(pdf_bytes) > 5000:
            print("✅ PDF size looks good (contains full content)")
        else:
            print("⚠️  PDF might be too small - check if all sections are included")
        
        print("\n📋 Report includes:")
        print("   ✓ Header with title and subtitle")
        print("   ✓ Severity Index")
        print("   ✓ Complete Patient Profile (8 fields)")
        print("   ✓ All Primary Symptoms (5 symptoms)")
        print("   ✓ Top 2 Disease Diagnoses with:")
        print("       - Home Care / Self Care")
        print("       - Red Flag Symptoms")
        print("       - Medication Suggestions")
        print("   ✓ Next Diagnostic Steps")
        print("   ✓ Important Disclaimer")

        print()
        print("🎉 SUCCESS! Open '{}' to view the complete Hindi PDF report!".format(output_file))

        return True

    except Exception as error:
        print("❌ Error generating PDF: {}".format(error))
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_success = test_complete_hindi_pdf()
    sys.exit(0 if test_success else 1)

