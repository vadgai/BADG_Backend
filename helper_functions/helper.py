from fpdf import FPDF

def convert_to_pdf(report, output_pdf_path):
    try:
       
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
 
        pdf.add_page()

        pdf.set_title("Medical Consultation Report")
        pdf.set_author("AI Assistant")
        
   
        pdf.set_font("Arial", "B", size=16) 
        pdf.cell(200, 10, txt="Medical Consultation Report", ln=True, align="C")
        pdf.ln(10)  
        

        pdf.set_font("Arial", size=12)


        lines = report.split('\n')

        for line in lines:
            pdf.multi_cell(0, 10, line)
        
       
        pdf.set_y(-15)
        pdf.set_font("Arial", "I", 8)
        pdf.cell(0, 10, f"Page {pdf.page_no()}", 0, 0, "C")

        
        pdf.output(output_pdf_path)
        
       
        print(f"PDF generated successfully at {output_pdf_path}")
        return True  

    except Exception as e:
       
        print(f"Error generating PDF: {e}")
        return False  
