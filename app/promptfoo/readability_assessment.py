from typing import Dict, Union, Any
import textdescriptives as td
import numpy as np

def get_assert(output: str, context) -> Union[bool, float, Dict[str, Any]]:
    """
    Assess the readability of the output text using TextDescriptives instead of py-readability-metrics.
    Returns a GradingResult with component scores for different readability metrics.
    """
    print("=== TEXTDESCRIPTIVES READABILITY ASSESSMENT STARTING ===")
    print(f"Output to assess: {output}")
    
    try:
        if not output or len(output.strip()) == 0:
            return {
                'pass': False,
                'score': 0.0,
                'reason': 'Empty or invalid output text'
            }
        
        # Use TextDescriptives to calculate readability metrics
        metrics_df = td.extract_metrics(
            text=output, 
            spacy_model="en_core_web_sm", 
            metrics=["readability"]
        )
        
        # Extract the readability metrics and convert from numpy types to Python native types
        flesch_reading_ease = float(metrics_df["flesch_reading_ease"].iloc[0])
        flesch_kincaid_grade = float(metrics_df["flesch_kincaid_grade"].iloc[0])
        gunning_fog = float(metrics_df["gunning_fog"].iloc[0])
        coleman_liau_index = float(metrics_df["coleman_liau_index"].iloc[0])
        
        # Set thresholds for readability
        MAX_GRADE_LEVEL = 12.0  # Maximum acceptable grade level (high school)
        MIN_FLESCH_EASE = 50.0  # Minimum acceptable Flesch Reading Ease score
        
        # Calculate average grade level from metrics
        grade_levels = [flesch_kincaid_grade, gunning_fog, coleman_liau_index]
        avg_grade_level = sum(grade_levels) / len(grade_levels)
        
        # Determine if the text passes readability requirements
        passes_grade_level = bool(avg_grade_level <= MAX_GRADE_LEVEL)
        passes_flesch_ease = bool(flesch_reading_ease >= MIN_FLESCH_EASE)
        
        # Calculate normalized score (0-1)
        grade_level_score = float(max(0, 1 - (avg_grade_level / (MAX_GRADE_LEVEL * 1.5))))
        flesch_ease_score = float(flesch_reading_ease / 100.0)
        
        # Overall score is average of both metrics
        overall_score = float((grade_level_score + flesch_ease_score) / 2)
        
        # Ensure all values are standard Python types, not numpy types
        def numpy_to_python(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, dict):
                return {k: numpy_to_python(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [numpy_to_python(i) for i in obj]
            else:
                return obj
        
        # Return comprehensive grading result
        result = {
            'pass': passes_grade_level and passes_flesch_ease,
            'score': overall_score,
            'reason': f'Readability assessment: Average grade level: {avg_grade_level:.1f}, Flesch ease: {flesch_reading_ease:.1f}',
            'componentResults': [
                {
                    'pass': passes_grade_level,
                    'score': grade_level_score,
                    'reason': f'Grade Level (target ≤ {MAX_GRADE_LEVEL}): {avg_grade_level:.1f}'
                },
                {
                    'pass': passes_flesch_ease,
                    'score': flesch_ease_score,
                    'reason': f'Flesch Reading Ease (target ≥ {MIN_FLESCH_EASE}): {flesch_reading_ease:.1f}'
                }
            ],
            'namedScores': {
                'flesch_kincaid_grade': flesch_kincaid_grade,
                'flesch_ease': flesch_reading_ease,
                'gunning_fog_grade': gunning_fog,
                'coleman_liau_grade': coleman_liau_index,
                'avg_grade_level': avg_grade_level
            }
        }
        
        # Convert any remaining numpy types to Python native types
        result = numpy_to_python(result)
        
        print("Assessment result:", result)
        return result
        
    except Exception as e:
        print(f"Error in readability assessment: {str(e)}")
        return {
            'pass': False,
            'score': 0.0,
            'reason': f'Error in readability assessment: {str(e)}'
        } 