module.exports = function (varName, prompt, otherVars) {
  // Generate a unique ID using timestamp and a random component
  const uniqueId = 'promptfoo-eval-test-' + Date.now().toString() + '-' + Math.random().toString(36).substring(2, 9);
  return {
    output: uniqueId
  };
}; 