export function sseBody(events: object[]): string {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
}
