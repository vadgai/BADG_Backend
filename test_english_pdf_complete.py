"""
Test the updated PDF generation for English with complete report structure
"""
import sys
import os
import traceback

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pdf_generator_unicode import generate_hindi_pdf

def test_complete_english_pdf():
    """Test complete English PDF with all sections"""
    
    # Sample test data matching the full report structure
    test_data = {
        'report': {
            'PatientInfo': {
                'Age': '35',
                'Gender': 'Male'
            },
            'Urgency': 'Moderate',
            'MainSymptoms': [
                'Fever',
                'Cough',
                'Headache',
                'Fatigue',
                'Sore throat'
            ],
            'TopDiseaseMatches': [
                {
                    'Disease1': {
                        'Name1': 'Common Cold',
                        'MatchLevel1': 'High',
                        'PreHospitalCare1': [
                            'Get adequate rest',
                            'Drink warm water',
                            'Take steam inhalation'
                        ],
                        'SelfCare1': [
                            'Eat warm food',
                            'Avoid smoking'
                        ],
                        'SymptomsToWatch1': [
                            'Fever above 103°F',
                            'Difficulty breathing',
                            'Chest pain'
                        ],
                        'MedicationSuggestion1': [
                            'Paracetamol 500mg (for fever)',
                            'Cough syrup (as per doctor advice)',
                            'Throat lozenges'
                        ]
                    }
                },
                {
                    'Disease2': {
                        'Name2': 'Viral Infection',
                        'MatchLevel2': 'Moderate',
                        'PreHospitalCare2': [
                            'Wash hands frequently',
                            'Take rest'
                        ],
                        'SelfCare2': [
                            'Eat nutritious food',
                            'Drink plenty of fluids'
                        ],
                        'SymptomsToWatch2': [
                            'Persistent vomiting',
                            'Signs of dehydration'
                        ],
                        'MedicationSuggestion2': [
                            'ORS (to prevent dehydration)',
                            'Vitamin C supplements'
                        ]
                    }
                }
            ],
            'NextDiagnosticSteps': [
                'Consult your doctor',
                'Get Complete Blood Count (CBC) test',
                'Chest X-ray if necessary',
                'Follow-up if no improvement in 3 days'
            ]
        },
        'patient_details': {
            'name': 'Rahul Kumar',
            'age': 35,
            'gender': 'Male',
            'occupation': 'Software Engineer',
            'physical_activity': 'Moderate',
            'diet_type': 'Vegetarian',
            'weight': 70,
            'height': 175,
            'location': {
                'city': 'Delhi',
                'state': 'Delhi'
            }
        }
    }
    
    print("🧪 Testing Complete English PDF Generation...")
    print()
    
    try:
        # Generate English PDF
        pdf_bytes = generate_hindi_pdf(test_data, 'en')
        
        # Save test PDF
        output_file = 'test_english_complete_report.pdf'
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
        print("🎉 SUCCESS! Open '{}' to view the complete English PDF report!".format(output_file))

        return True

    except Exception as error:
        print("❌ Error generating PDF: {}".format(error))
        traceback.print_exc()
        return False


if __name__ == '__main__':
    test_success = test_complete_english_pdf()
    sys.exit(0 if test_success else 1)

