/**
 * Artillery processor for custom performance metrics
 */

module.exports = {
  // Called before each scenario
  beforeScenario: function(context, events, done) {
    context.vars.scenarioStart = Date.now();
    return done();
  },

  // Called after each scenario
  afterScenario: function(context, events, done) {
    const scenarioDuration = Date.now() - context.vars.scenarioStart;

    // Emit custom metric for scenario duration
    events.emit('customStat', {
      stat: 'scenario_duration',
      value: scenarioDuration
    });

    return done();
  },

  // Custom response handler
  logResponse: function(requestParams, response, context, events, done) {
    // Log slow responses for debugging
    if (response.timings && response.timings.response > 1000) {
      console.log(`[SLOW RESPONSE] ${requestParams.url}: ${response.timings.response}ms`);
    }

    // Track specific endpoint performance
    const endpoint = requestParams.url;
    if (response.timings) {
      events.emit('customStat', {
        stat: `endpoint_${endpoint.replace(/[^a-zA-Z0-9]/g, '_')}_response_time`,
        value: response.timings.response
      });
    }

    return done();
  },

  // Validate health check responses
  validateHealthCheck: function(requestParams, response, context, events, done) {
    try {
      const body = JSON.parse(response.body);
      if (body.status === 'healthy') {
        events.emit('customStat', {
          stat: 'health_check_success',
          value: 1
        });
      } else {
        events.emit('customStat', {
          stat: 'health_check_failure',
          value: 1
        });
        console.log(`[HEALTH CHECK FAILED] Status: ${body.status}`);
      }
    } catch (error) {
      events.emit('customStat', {
        stat: 'health_check_parse_error',
        value: 1
      });
      console.log(`[HEALTH CHECK PARSE ERROR] ${error.message}`);
    }

    return done();
  }
};