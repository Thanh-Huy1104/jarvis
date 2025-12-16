# Data Analysis with Pandas

Read, analyze, and visualize data using pandas and matplotlib.

## Code

```python
import pandas as pd
import matplotlib.pyplot as plt

def analyze_csv(file_path):
    """
    Read and analyze a CSV file.
    """
    # Read the CSV
    df = pd.read_csv(file_path)
    
    # Basic statistics
    stats = df.describe()
    
    # Print summary
    print(f"Dataset shape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst few rows:\n{df.head()}")
    print(f"\nStatistics:\n{stats}")
    
    return df

# Example usage (adapt to your data)
# df = analyze_csv('data.csv')
```

## Usage Examples

- Load and explore CSV files
- Calculate statistics on datasets
- Perform data transformations
- Create visualizations
