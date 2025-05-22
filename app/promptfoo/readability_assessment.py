from typing import Dict, Union, Any
import textdescriptives as td
import numpy as np

# Readability thresholds
MAX_GRADE_LEVEL = 12.0  # Maximum acceptable grade level (high school)
MIN_FLESCH_EASE = 50.0  # Minimum acceptable Flesch Reading Ease score

def _calculate_readability_metrics(metrics_df) -> Dict[str, float]:
    # Extract the readability metrics and convert from numpy types to Python native types
    flesch_reading_ease = float(metrics_df["flesch_reading_ease"].iloc[0])
    flesch_kincaid_grade = float(metrics_df["flesch_kincaid_grade"].iloc[0])
    gunning_fog = float(metrics_df["gunning_fog"].iloc[0])
    coleman_liau_index = float(metrics_df["coleman_liau_index"].iloc[0])
    
    # Calculate average grade level
    grade_levels = [flesch_kincaid_grade, gunning_fog, coleman_liau_index]
    avg_grade_level = sum(grade_levels) / len(grade_levels)
    
    return {
        "flesch_kincaid_grade": flesch_kincaid_grade,
        "flesch_ease": flesch_reading_ease,
        "gunning_fog_grade": gunning_fog,
        "coleman_liau_grade": coleman_liau_index,
        "avg_grade_level": avg_grade_level
    }

def get_assert(output: str) -> Union[bool, float, Dict[str, Any]]:
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
        
        # Get readability metrics
        metrics = _calculate_readability_metrics(metrics_df)
        flesch_reading_ease = metrics["flesch_ease"]
        avg_grade_level = metrics["avg_grade_level"]
        
        # Determine if the text passes readability requirements
        passes_grade_level = bool(avg_grade_level <= MAX_GRADE_LEVEL)
        passes_flesch_ease = bool(flesch_reading_ease >= MIN_FLESCH_EASE)
        
        # Calculate normalized score (0-1)
        grade_level_score = float(max(0, 1 - (avg_grade_level / (MAX_GRADE_LEVEL * 1.5))))
        flesch_ease_score = float(flesch_reading_ease / 100.0)
        
        # Overall score is average of both metrics
        overall_score = float((grade_level_score + flesch_ease_score) / 2)
        
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
            'namedScores': metrics
        }
        
        print("Assessment result:", result)
        return result
        
    except Exception as e:
        print(f"Error in readability assessment: {e}")
        return {
            'pass': False,
            'score': -1.0,  # Negative score indicates error processing input
            'reason': f'Error in readability assessment: {e}'
        } 