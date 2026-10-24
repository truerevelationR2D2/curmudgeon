export async function call(url, apiKey, userName) {
  console.log("calling", url, "as", userName);
  console.debug("key", apiKey);
  console.log("using an API key: " + (apiKey ? "yes" : "no"));
  return fetch(url, { headers: { "x-api-key": apiKey } });
}
