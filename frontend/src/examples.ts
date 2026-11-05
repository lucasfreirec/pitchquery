export interface Example {
  label: string
  query: string
}

export const EXAMPLES: Example[] = [
  {
    label: 'Golden Boot race',
    query: 'shots where outcome = "Goal" and period < 5 | count by player | sort desc | limit 10',
  },
  {
    label: 'Late big chances for Argentina',
    query: 'shots where xg > 0.3 and team = "Argentina" and minute >= 80',
  },
  {
    label: "Messi's completed passes into the last 18 yards",
    query: 'passes where player = "Lionel Messi" and outcome = "complete" and end_x > 102',
  },
  {
    label: 'Shots and dribbles under pressure',
    query: 'events where type in ("Shot", "Dribble") and under_pressure = true',
  },
  {
    label: "France's top shooters",
    query: 'shots where team = "France" | count by player | sort desc | limit 5',
  },
  {
    label: 'Every shot of the final',
    query: 'shots where match_id = 3869685 and period < 5',
  },
]
