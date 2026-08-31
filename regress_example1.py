import numpy as np
import matplotlib
matplotlib.use('qtagg')
import matplotlib.pyplot as plt
from scipy import stats

rng = np.random.default_rng()
x = rng.random(10)
y = 1.6*x + rng.random(10)

res = stats.linregress(x, y)
print(f"R-squared: {res.rvalue**2:.6f}")

plt.plot(x, y, 'o', label='original data')
plt.plot(x, res.intercept + res.slope*x, 'r', label='fitted line')
plt.legend()
plt.show()