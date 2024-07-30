from flask import Flask, render_template, request
import csv
import os
import requests
from lxml import etree
from collections import defaultdict

app = Flask(__name__)

# Define the path to the CSV file
CSV_FILE = 'data.csv'

# Check if the CSV file exists; if not, create it and write the header
def initialize_csv():
    if not os.path.isfile(CSV_FILE):
        with open(CSV_FILE, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Answer Key Link', 'Category', 'Roll Number', 'Candidate Name', 'Venue Name', 'Exam Date', 'Exam Time', 'Total Marks'])  # Write header

initialize_csv()

def is_roll_number_exists(roll_number):
    with open(CSV_FILE, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['Roll Number'] == roll_number:
                return True
    return False

def calculate_rank(roll_number, category):
    with open(CSV_FILE, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        candidates = sorted(reader, key=lambda x: float(x['Total Marks']), reverse=True)

        overall_rank = None
        category_rank = None
        category_candidates = [candidate for candidate in candidates if candidate['Category'] == category]

        for rank, candidate in enumerate(candidates, start=1):
            if candidate['Roll Number'] == roll_number:
                overall_rank = rank

        for rank, candidate in enumerate(category_candidates, start=1):
            if candidate['Roll Number'] == roll_number:
                category_rank = rank

        return overall_rank, category_rank

def calculate_shift_averages_and_ranks():
    with open(CSV_FILE, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        shift_data = defaultdict(list)
        shift_candidates = defaultdict(list)
        
        for row in reader:
            shift = f"{row['Exam Date']} {row['Exam Time']}"
            shift_data[shift].append(float(row['Total Marks']))
            shift_candidates[shift].append({
                'Roll Number': row['Roll Number'],
                'Total Marks': float(row['Total Marks'])
            })
        
        shift_averages = {shift: sum(marks) / len(marks) for shift, marks in shift_data.items()}
        shift_ranks = {}
        
        for shift, candidates in shift_candidates.items():
            sorted_candidates = sorted(candidates, key=lambda x: x['Total Marks'], reverse=True)
            for rank, candidate in enumerate(sorted_candidates, start=1):
                candidate['Shift Rank'] = rank
            shift_ranks[shift] = {c['Roll Number']: c['Shift Rank'] for c in sorted_candidates}
        
        return shift_averages, shift_ranks

def calculate_averages():
    with open(CSV_FILE, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        total_marks = []
        category_marks = defaultdict(list)
        
        for row in reader:
            total_marks.append(float(row['Total Marks']))
            category_marks[row['Category']].append(float(row['Total Marks']))

        overall_average = sum(total_marks) / len(total_marks) if total_marks else 0
        category_averages = {category: sum(marks) / len(marks) for category, marks in category_marks.items()}
        
        return overall_average, category_averages

@app.route('/', methods=['GET', 'POST'])
def index():
    content = {}
    if request.method == 'POST':
        answer_key_link = request.form['answerKeyLink']
        category = request.form['category']
        
        # Fetch and parse the HTML content
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(answer_key_link, headers=headers)
            response.raise_for_status()  # Raise an error for bad responses
            
            parser = etree.HTMLParser()
            tree = etree.fromstring(response.content, parser)

            # Extract data using specified XPaths
            roll_number = tree.xpath('/html/body/div/div[2]/table/tbody/tr[1]/td[2]/text()')
            candidate_name = tree.xpath('/html/body/div/div[2]/table/tbody/tr[2]/td[2]/text()')
            venue_name = tree.xpath('/html/body/div/div[2]/table/tbody/tr[3]/td[2]/text()')
            exam_date = tree.xpath('/html/body/div/div[2]/table/tbody/tr[4]/td[2]/text()')
            exam_time = tree.xpath('/html/body/div/div[2]/table/tbody/tr[5]/td[2]/text()')

            # Extract text and handle cases where content might not be found
            roll_number = roll_number[0].strip() if roll_number else 'Roll Number not found'
            candidate_name = candidate_name[0].strip() if candidate_name else 'Candidate Name not found'
            venue_name = venue_name[0].strip() if venue_name else 'Venue Name not found'
            exam_date = exam_date[0].strip() if exam_date else 'Exam Date not found'
            exam_time = exam_time[0].strip() if exam_time else 'Exam Time not found'

            # Initialize variables for marks calculation
            total_subjects = 4
            questions_per_subject = 25
            per_mcq_marks = 2
            wrong_ans_marks = 0.5
            total_right = 0
            total_not_attempted = 0

            # Iterate through subjects
            question_panels = tree.xpath('//div[contains(@class, "question-pnl")]')
            for s in range(total_subjects):
                right = 0
                not_attempted = 0

                # Iterate through questions for each subject
                for i in range(questions_per_subject * s, questions_per_subject * s + questions_per_subject):
                    question_panel = question_panels[i]
                    bold_texts = question_panel.xpath('.//td[contains(@class, "bold")]')
                    answer_text = bold_texts[9].text.strip() if len(bold_texts) > 9 else "--"
                    print(answer_text)

                    # Check if the question was not attempted
                    if answer_text == "--":
                        not_attempted += 1
                    else:
                        # Try to check if the answer is correct
                        try:
                            correct_answer = question_panel.xpath('.//td[contains(@class, "rightAns")]/text()')[0][0]
                            if correct_answer == answer_text:
                                right += 1
                        except Exception as e:
                            print(f"Error parsing question at index {i} in subject {s}: {e}")
                            pass

                total_not_attempted += not_attempted
                total_right += right

            # Calculate the total marks
            total_questions = total_subjects * questions_per_subject
            total_wrong = total_questions - total_right - total_not_attempted
            total_marks = total_right * per_mcq_marks - total_wrong * wrong_ans_marks

            # Store data in CSV file
            # Store data in CSV file only if roll number does not exist
            if not is_roll_number_exists(roll_number):
                with open(CSV_FILE, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([answer_key_link, category, roll_number, candidate_name, venue_name, exam_date, exam_time, total_marks])
            
            # Calculate ranks
            overall_rank, category_rank = calculate_rank(roll_number, category)
            
            # Calculate shift averages and ranks
            shift_averages, shift_ranks = calculate_shift_averages_and_ranks()
            shift_key = f"{exam_date} {exam_time}"
            average_marks_for_shift = shift_averages.get(shift_key, 'No data for this shift')
            shift_rank = shift_ranks.get(shift_key, {}).get(roll_number, 'No data for this shift')
            
            # Calculate overall and category averages
            overall_average, category_averages = calculate_averages()
            
            # Prepare content for display
            content = {
                'Roll Number': roll_number,
                'Candidate Name': candidate_name,
                'Venue Name': venue_name,
                'Exam Date': exam_date,
                'Exam Time': exam_time,
                'Total Marks': total_marks,
                'Overall Rank': overall_rank,
                'Category Rank': category_rank,
                'Average Marks for Shift': average_marks_for_shift,
                'Shift Rank': shift_rank,
                'Overall Average Marks': overall_average,
                'Category Averages': category_averages.get(category, 'No data for this category')
            }
        except requests.RequestException as e:
            content = {'Error': f'Error fetching content: {e}'}
        
        return render_template('index.html', content=content)

    return render_template('index.html', content=content)

if __name__ == '__main__':
    app.run(debug=True)
