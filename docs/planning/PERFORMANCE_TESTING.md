# Performance Testing Guide

SysManage includes comprehensive performance testing capabilities using Playwright for UI performance and Artillery for backend load testing, with multi-OS support and automated regression detection.

## Overview

### Performance Testing Components

- **Playwright Performance Tests** - UI load times, Core Web Vitals, memory usage
- **Artillery Load Tests** - API response times, throughput, error rates
- **Cross-Browser Performance** - Chrome, Firefox, WebKit/Safari (macOS only)
- **Multi-OS Testing** - Linux, macOS, Windows
- **Regression Detection** - Statistical analysis with tolerance bands

## Running Performance Tests

### Local Testing

```bash
# Run all performance tests (Artillery + Playwright + regression analysis)
make test-performance

# Run all tests including performance
make test

# Run specific performance tests
PYTHONPATH=tests/ui:$PYTHONPATH python -m pytest tests/ui/test_performance_playwright.py -v

# Run Artillery load tests only
artillery run artillery.yml --output artillery-report.json
artillery report artillery-report.json --output artillery-report.html
```

### Performance Test Requirements

**System Requirements:**
- Python 3.12+
- Node.js 22.13+ (Artillery requirement; works with warnings on 20.x)
- Artillery (`npm install -g artillery@latest`)
- Playwright browsers (`playwright install`)

**Platform Support:**
- ✅ **Linux** - Full support (Playwright + Artillery)
- ✅ **macOS** - Full support (Playwright + Artillery + WebKit)
- ✅ **Windows** - Playwright only (Artillery may have compatibility issues)
- ✅ **FreeBSD** - Full support via npm
- ❌ **OpenBSD** - Playwright only (Artillery not reliable)

## Performance Metrics Collected

### Playwright UI Metrics

```javascript
{
  "navigation": {
    "domContentLoaded": 250,     // DOM ready time (ms)
    "loadComplete": 450,         // Full page load (ms)
    "firstByte": 50              // Time to first byte (ms)
  },
  "paint": {
    "firstPaint": 180,           // First paint time (ms)
    "firstContentfulPaint": 220  // First contentful paint (ms)
  },
  "resources": {
    "total": 15,                 // Number of resources loaded
    "totalSize": 524288          // Total transfer size (bytes)
  },
  "memory": {
    "used": 12582912,            // Memory usage (bytes)
    "total": 268435456           // Total heap size (bytes)
  }
}
```

### Artillery Load Test Metrics

```yaml
scenarios:
  - name: "Health Check"        # API health endpoint
  - name: "Authentication Flow" # Login/JWT validation
  - name: "Host Management"     # CRUD operations
  - name: "WebSocket Test"      # Real-time connections

performance_budgets:
  p95: 500ms                    # 95th percentile response time
  p99: 1000ms                   # 99th percentile response time
  maxErrorRate: 1%              # Maximum error rate
  minRPS: 8                     # Minimum requests per second
```

## Performance Budgets & Thresholds

### UI Performance Budgets

| Metric | Budget | Critical |
|--------|--------|----------|
| Page Load Time | < 5.0s | < 10.0s |
| First Contentful Paint | < 2.0s | < 4.0s |
| DOM Content Loaded | < 1.5s | < 3.0s |
| Login Flow Time | < 3.0s | < 6.0s |
| Average Response Time | < 0.5s | < 1.0s |

### Load Test Budgets

| Metric | Budget | Critical |
|--------|--------|----------|
| P95 Response Time | < 500ms | < 1000ms |
| P99 Response Time | < 1000ms | < 2000ms |
| Error Rate | < 1% | < 5% |
| Min Throughput | > 8 RPS | > 4 RPS |

## Regression Detection

### Statistical Analysis

The regression detector uses:
- **Rolling Baseline** - Average of last 10 runs
- **Tolerance Bands** - ±15% or 2 standard deviations (whichever is more generous)
- **Sustained Regressions** - 3+ consecutive failures to avoid false positives

### Example Regression Analysis

```bash
🔍 Performance Regression Analysis
==================================================
Dom Content Loaded:
  Current: 280.00
  Baseline: 245.50
  Status: 14.0% increase (within 15.0% tolerance)
  ✅ Within acceptable range

First Contentful Paint:
  Current: 450.00
  Baseline: 220.00
  Status: 104.5% increase (threshold: 15.0%)
  ⚠️ REGRESSION DETECTED!

Response Time P95:
  Current: 320.00
  Baseline: 310.25
  Status: 3.1% increase (within 15.0% tolerance)
  ✅ Within acceptable range
```

## CI/CD Integration

### Multi-OS GitHub Actions

The CI/CD pipeline runs performance tests on:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]

test-ui-performance:
  - Playwright cross-browser testing with performance metrics
  - Artillery load testing (Linux/macOS only)
  - Performance regression analysis
  - Artifact collection (reports, screenshots, videos)
```

### Performance Artifacts

- `performance-results.json` - Playwright metrics
- `artillery-report-*.json` - Load test raw data
- `artillery-report-*.html` - Load test reports
- `performance-summary.md` - Cross-platform analysis
- `performance-history.json` - Historical baseline data

## Configuring Performance Tests

### Artillery Configuration (`artillery.yml`)

```yaml
config:
  target: 'http://localhost:8001'
  phases:
    - duration: 10, arrivalRate: 2   # Warm-up
    - duration: 30, arrivalRate: 5   # Normal load
    - duration: 20, arrivalRate: 10  # Peak load

  ensure:
    p95: 500                         # Performance budgets
    p99: 1000
    maxErrorRate: 1
    minRPS: 8
```

### Playwright Performance Tests

```python
# Custom performance metrics collection
async def collect_performance_metrics(page: Page, browser_name: str):
    metrics = await page.evaluate("""
        () => {
            const navigation = performance.getEntriesByType('navigation')[0];
            const paintEntries = performance.getEntriesByType('paint');
            return {
                domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                firstContentfulPaint: paintEntries.find(entry => entry.name === 'first-contentful-paint')?.startTime || 0,
                resourceCount: performance.getEntriesByType('resource').length,
                memoryUsed: performance.memory ? performance.memory.usedJSHeapSize : null
            };
        }
    """)
    return metrics
```

## Troubleshooting Performance Tests

### Common Issues

**Artillery not found:**
```bash
npm install -g artillery@latest
```

**Playwright browsers not installed:**
```bash
playwright install chromium firefox
# macOS only:
playwright install webkit
```

**Permission issues (Linux):**
```bash
sudo apt-get update
sudo apt-get install -y libnss3 libnspr4 libdbus-1-3 libatk1.0-0
```

**Server not starting:**
```bash
# Check if ports are available
lsof -i :8001
lsof -i :7443

# Kill existing processes
pkill -f "uvicorn.*sysmanage"
```

### Performance Test Failures

**High response times:**
- Check system load during testing
- Verify database connections
- Review server logs for errors

**Memory leaks detected:**
- Monitor memory usage trends
- Check for unclosed connections
- Review browser console errors

**Flaky test results:**
- Increase warm-up duration
- Add network stability checks
- Review tolerance band settings

## Best Practices

### Local Development

1. **Baseline establishment** - Run tests 3-5 times after changes
2. **Clean environment** - Close unnecessary applications
3. **Consistent conditions** - Same network, power settings
4. **Monitor trends** - Watch for gradual degradation

### CI/CD Pipeline

1. **Fail-fast strategy** - Stop on critical regressions
2. **Artifact collection** - Save reports for analysis
3. **Historical tracking** - Maintain performance baselines
4. **Cross-platform validation** - Test on all target platforms

### Performance Optimization

1. **Profile before optimizing** - Identify actual bottlenecks
2. **Measure impact** - Quantify improvements
3. **Test across browsers** - Ensure consistent performance
4. **Monitor production** - Compare test vs real-world metrics

## Integration with Existing Tests

Performance tests integrate seamlessly with the existing test suite:

```bash
# Full test suite with performance
make test                    # Python + TypeScript + UI + Performance

# Individual test categories
make test-python            # Backend tests only
make test-typescript        # Frontend tests only
make test-playwright        # UI tests only
make test-performance       # Performance tests only
```

This comprehensive performance testing setup ensures SysManage maintains excellent performance across all platforms while catching regressions early in the development cycle.