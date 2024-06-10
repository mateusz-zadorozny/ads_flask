from flask import Flask, render_template, request
import csv
from scipy.stats import ttest_ind
import logging

app = Flask(__name__)

# Set up logging to console only
# logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze(): 
    currency = request.form['currency']
    file = request.files['file']
    
    try:
        # Ensure the file is read in text mode
        data = []
        stream = file.stream.read().decode("utf-8").splitlines()
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames
        app.logger.debug(f"Fieldnames: {fieldnames}")  # Log the fieldnames for debugging
        
        for row in reader:
            app.logger.debug(f"Row: {row}")  # Log each row for debugging
            data.append(row)
        
        # Ensure consistency in column names and check required columns
        required_columns = ['Results', 'Time of day (ad account time zone)', f'Amount spent ({currency})']
        if not all(column in fieldnames for column in required_columns):
            raise ValueError(f"<br>Missing required columns. Found columns: {fieldnames}<br>")
        
        # Process data
        hourly_data = {}
        for row in data:
            hour = int(row['Time of day (ad account time zone)'][:2])
            results = float(row['Results']) if row['Results'] else 0
            amount_spent = float(row[f'Amount spent ({currency})']) if row[f'Amount spent ({currency})'] else 0
            
            if hour not in hourly_data:
                hourly_data[hour] = {'Results': 0, 'Amount spent': 0}
            hourly_data[hour]['Results'] += results
            hourly_data[hour]['Amount spent'] += amount_spent

        # Calculate cost per result
        for hour in hourly_data:
            if hourly_data[hour]['Results'] == 0:
                hourly_data[hour]['Cost per Result'] = 0
            else:
                hourly_data[hour]['Cost per Result'] = hourly_data[hour]['Amount spent'] / hourly_data[hour]['Results']

        # Calculate current average cost per result
        total_results = sum(hourly_data[hour]['Results'] for hour in hourly_data)
        total_cost = sum(hourly_data[hour]['Amount spent'] for hour in hourly_data)
        current_avg_cost = total_cost / total_results if total_results != 0 else 0

        # Function to find the worst consecutive hours for a given window size
        def find_worst_hours(window_size):
            worst_consecutive_hours = []
            worst_avg_cost = 0

            for start_hour in range(24):
                hours_block = [(start_hour + i) % 24 for i in range(window_size)]
                total_cost_worst_hours = sum(hourly_data[hour]['Amount spent'] for hour in hours_block)
                total_results_worst_hours = sum(hourly_data[hour]['Results'] for hour in hours_block)
                avg_cost_worst_hours = (total_cost_worst_hours / total_results_worst_hours) if total_results_worst_hours != 0 else 0

                if avg_cost_worst_hours > worst_avg_cost:
                    worst_avg_cost = avg_cost_worst_hours
                    worst_consecutive_hours = hours_block

            total_cost_worst_hours = sum(hourly_data[hour]['Amount spent'] for hour in worst_consecutive_hours)
            total_results_worst_hours = sum(hourly_data[hour]['Results'] for hour in worst_consecutive_hours)
            avg_cost_worst_hours = (total_cost_worst_hours / total_results_worst_hours) if total_results_worst_hours != 0 else 0

            remaining_hours = [hour for hour in hourly_data if hour not in worst_consecutive_hours]
            total_cost_remaining_hours = sum(hourly_data[hour]['Amount spent'] for hour in remaining_hours)
            total_results_remaining_hours = sum(hourly_data[hour]['Results'] for hour in remaining_hours)
            avg_cost_remaining_hours = (total_cost_remaining_hours / total_results_remaining_hours) if total_results_remaining_hours != 0 else 0

            improvement_percentage = ((current_avg_cost - avg_cost_remaining_hours) / current_avg_cost) * 100 if current_avg_cost != 0 else 0
            t_stat, p_value = ttest_ind(
                [hourly_data[hour]['Cost per Result'] for hour in remaining_hours],
                [hourly_data[hour]['Cost per Result'] for hour in worst_consecutive_hours]
            )

            return {
                'window_size': window_size,
                'worst_consecutive_hours': worst_consecutive_hours,
                'current_avg_cost': round(current_avg_cost, 2),
                'avg_cost_worst_hours': round(avg_cost_worst_hours, 2),
                'avg_cost_remaining_hours': round(avg_cost_remaining_hours, 2),
                'improvement_percentage': round(improvement_percentage, 2),
                'p_value': round(p_value, 4)
            }

        results = []
        for window_size in range(3, 13):
            result = find_worst_hours(window_size)
            results.append(result)

        significant_results = [res for res in results if res['p_value'] < 0.05]

        if significant_results:
            best_significant_result = max(significant_results, key=lambda x: x['improvement_percentage'])
            recommendation = {
                'message': "Best Window Size for Improvement (with p-value < 0.05):",
                'window_size': best_significant_result['window_size'],
                'worst_consecutive_hours': best_significant_result['worst_consecutive_hours'],
                'current_avg_cost': best_significant_result['current_avg_cost'],
                'avg_cost_worst_hours': best_significant_result['avg_cost_worst_hours'],
                'avg_cost_remaining_hours': best_significant_result['avg_cost_remaining_hours'],
                'improvement_percentage': best_significant_result['improvement_percentage'],
                'p_value': best_significant_result['p_value'],
                'style': "success"
            }
        else:
            closest_result = min(results, key=lambda x: abs(x['p_value'] - 0.05))
            recommendation = {
                'message': "No window size has a p-value < 0.05<br> Showing the closest result:",
                'window_size': closest_result['window_size'],
                'worst_consecutive_hours': closest_result['worst_consecutive_hours'],
                'current_avg_cost': closest_result['current_avg_cost'],
                'avg_cost_worst_hours': closest_result['avg_cost_worst_hours'],
                'avg_cost_remaining_hours': closest_result['avg_cost_remaining_hours'],
                'improvement_percentage': closest_result['improvement_percentage'],
                'p_value': closest_result['p_value'],
                'style': "warning"
            }

        return render_template('result.html', recommendation=recommendation, currency=currency)

    except (ValueError, KeyError, csv.Error) as e:
        app.logger.error(f"Error: {str(e)}")
        error_message = f"<span style='color:var(--light-danger)'>Sorry - the file contents are wrong.</span><br>{str(e)}<br>Your file must have the following columns:<br><ul><li>Results</li><li>Time of day (ad account time zone)</li><li>Amount spent (XXX)</li></ul>Where XXX must match the selected currency."
        return render_template('index.html', error_message=error_message)

if __name__ == '__main__':
    app.run(debug=False)
