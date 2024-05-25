from flask import Flask, render_template, request
import pandas as pd
from scipy.stats import ttest_ind

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    currency = request.form['currency']
    file = request.files['file']
    
    try:
        new_data_set = pd.read_csv(file)

        # Ensure consistency in column names
        new_data_set.columns = new_data_set.columns.str.strip()

        # Check if necessary columns are present
        required_columns = ['Results', 'Time of day (ad account time zone)', f'Amount spent ({currency})']
        if not all(column in new_data_set.columns for column in required_columns):
            raise ValueError

        # Extract hour from the 'Time of day (ad account time zone)' column
        new_data_set['Hour'] = new_data_set['Time of day (ad account time zone)'].str.slice(0, 2).astype(int)

        # Clean up any potential NaNs in the 'Results' and amount spent columns (replace with 0)
        new_data_set['Results'] = new_data_set['Results'].fillna(0)
        amount_spent_column = f'Amount spent ({currency})'
        new_data_set[amount_spent_column] = new_data_set[amount_spent_column].fillna(0)

        # Group by hour and calculate total Results, total cost, and cost per result
        hourly_new_data_set = new_data_set.groupby('Hour').agg({
            'Results': 'sum',
            amount_spent_column: 'sum'
        }).reset_index()

        # Calculate cost per result
        hourly_new_data_set['Cost per Result'] = hourly_new_data_set[amount_spent_column] / hourly_new_data_set['Results']
        hourly_new_data_set['Cost per Result'] = hourly_new_data_set['Cost per Result'].replace([float('inf'), -float('inf')], 0)

        # Calculate current average cost per result
        current_total_results = hourly_new_data_set['Results'].sum()
        current_total_cost = hourly_new_data_set[amount_spent_column].sum()
        current_avg_cost = current_total_cost / current_total_results

        # Function to find the worst consecutive hours for a given window size
        def find_worst_hours(window_size):
            worst_consecutive_hours = []
            worst_avg_cost = 0

            for start_hour in range(24):
                hours_block = [(start_hour + i) % 24 for i in range(window_size)]
                consecutive_hours_data = hourly_new_data_set[hourly_new_data_set['Hour'].isin(hours_block)]
                total_cost_worst_hours = consecutive_hours_data[amount_spent_column].sum()
                total_results_worst_hours = consecutive_hours_data['Results'].sum()
                avg_cost_worst_hours = total_cost_worst_hours / total_results_worst_hours if total_results_worst_hours != 0 else 0

                if avg_cost_worst_hours > worst_avg_cost:
                    worst_avg_cost = avg_cost_worst_hours
                    worst_consecutive_hours = hours_block

            # Calculate total cost and results for the worst hours
            worst_hours_data = hourly_new_data_set[hourly_new_data_set['Hour'].isin(worst_consecutive_hours)]
            total_cost_worst_hours = worst_hours_data[amount_spent_column].sum()
            total_results_worst_hours = worst_hours_data['Results'].sum()
            avg_cost_worst_hours = total_cost_worst_hours / total_results_worst_hours if total_results_worst_hours != 0 else 0

            # Calculate total cost and results for the remaining hours
            remaining_hours_data = hourly_new_data_set[~hourly_new_data_set['Hour'].isin(worst_consecutive_hours)]
            total_cost_remaining_hours = remaining_hours_data[amount_spent_column].sum()
            total_results_remaining_hours = remaining_hours_data['Results'].sum()
            avg_cost_remaining_hours = total_cost_remaining_hours / total_results_remaining_hours if total_results_remaining_hours != 0 else 0

            # Calculate potential improvement
            improvement_percentage = ((current_avg_cost - avg_cost_remaining_hours) / current_avg_cost) * 100

            # Perform a t-test to compare the means
            t_stat, p_value = ttest_ind(remaining_hours_data['Cost per Result'], worst_hours_data['Cost per Result'])

            return {
                'window_size': window_size,
                'worst_consecutive_hours': worst_consecutive_hours,
                'current_avg_cost': round(current_avg_cost, 2),
                'avg_cost_worst_hours': round(avg_cost_worst_hours, 2),
                'avg_cost_remaining_hours': round(avg_cost_remaining_hours, 2),
                'improvement_percentage': round(improvement_percentage, 2),
                't_stat': round(t_stat, 2),
                'p_value': round(p_value, 4)
            }

        # Cycle through different window sizes and collect results
        results = []
        for window_size in range(3, 13):
            result = find_worst_hours(window_size)
            results.append(result)

        # Filter results to find those with p-value < 0.05
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
                't_stat': best_significant_result['t_stat'],
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
                't_stat': closest_result['t_stat'],
                'p_value': closest_result['p_value'],
                'style': "warning"
            }

        return render_template('result.html', recommendation=recommendation, currency=currency)
    
    except (ValueError, KeyError, pd.errors.EmptyDataError):
        error_message = "<span style='color:var(--danger)'>Sorry - the file contents are wrong.</span><br>Your file must have the following columns:<br><ul><li>Results</li><li>Time of day (ad account time zone)</li><li>Amount spent (XXX)</li></ul>Where XXX must match the selected currency."
        return render_template('index.html', error_message=error_message)

if __name__ == '__main__':
    app.run(debug=True)
