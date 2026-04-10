library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_mens_lacrosse_teamurls_2025.csv") %>% pull(3)

season = "2025"

root_url <- "https://stats.ncaa.org"

matchstatstibble = tibble()

matchstatsfilename <- paste0("data/ncaa_mens_lacrosse_matchstats_", season, ".csv")

for (i in urls){

  schoolpage <- i %>% read_html()

  if (str_detect(i, "org_id=282")) { # special case for Hobart
    schoolfull = 'Hobart Statesmen'
  } else {
    schoolfull <- schoolpage |> html_nodes(xpath = '/html/body/div[2]/div/div/div/div/div/div[1]/img') |> html_attr('alt')
#    schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  }

  message <- paste0("Adding ", schoolfull)

  print(message)

  matches <- schoolpage %>% html_nodes(xpath = '//*[@id="game_breakdown_div"]/table') %>% html_table()

  # doesn't handle postponed games right now (Hobart has one)
  # doesn't retain W/L, need to calculate that from score.

  matches <- matches[[1]] %>% slice(3:n()) %>% row_to_names(row_number = 1) %>% clean_names() %>%
    remove_empty(which = c("cols")) %>%
    mutate_all(na_if,"") %>%
    fill(c(date, result)) %>%
    mutate_at(vars(5:14),  replace_na, '0') %>%
    mutate(date = mdy(date), home_away = case_when(grepl("@",opponent) ~ "Away", TRUE ~ "Home"), opponent = gsub("@ ","",opponent)) %>%
    separate(result, into=c("score", "overtime"), sep = " \\(") %>%
    separate(score, into=c("home_score", "visitor_score")) %>%
    mutate(result = case_when(
      home_away == 'Home' & home_score < visitor_score ~ "L",
      home_away == 'Home' & home_score > visitor_score ~ "W",
      home_away == 'Away' & home_score > visitor_score ~ "L",
      home_away == 'Away' & home_score < visitor_score ~ "W",
    )
    ) |>
    mutate(team = schoolfull) %>%
    mutate(overtime = gsub(")", "", overtime)) %>%
    select(date, team, opponent, home_away, result, home_score, visitor_score, overtime, everything()) %>%
    clean_names() %>%
    mutate_at(vars(-date, -opponent, -home_away, -result, -team), ~str_replace(., "/", "")) %>%
    mutate_at(vars(-date, -team, -opponent, -home_away, -result, -overtime), as.numeric)

  teamside <- matches %>% filter(opponent != "Defensive Totals")

  opponentside <- matches %>% filter(opponent == "Defensive Totals") %>% select(-opponent, -home_away) %>% rename_with(.cols = 7:17, function(x){paste0("defensive_", x)}) |>  select(-result)

  joinedmatches <- inner_join(teamside, opponentside, by = c("date", "team", "home_score", "visitor_score", "overtime"))


  ### get goalie stats

  goalie_url <- str_c(i, "&year_stat_category_id=15650")
  goalie_page <- goalie_url |> read_html()
  g_matches <- goalie_page %>% html_nodes(xpath = '//*[@id="game_breakdown_div"]/table') %>% html_table()

  g_matches <- g_matches[[1]] %>% slice(3:n()) %>% row_to_names(row_number = 1) %>% clean_names() %>%
    remove_empty(which = c("cols")) %>%
    mutate_all(na_if,"") %>%
    fill(c(date, result)) |>
    mutate(date = mdy(date), home_away = case_when(grepl("@",opponent) ~ "Away", TRUE ~ "Home"), opponent = gsub("@ ","",opponent)) %>%
    separate(result, into=c("score", "overtime"), sep = " \\(") %>%
    separate(score, into=c("home_score", "visitor_score")) %>%
    mutate(g_min = str_replace(g_min, '/',''), goals_allowed = str_replace(goals_allowed, '/',''), saves = str_replace(saves, '/','')) |>
    mutate(g_min = ms(g_min), goals_allowed = as.integer(goals_allowed), saves = as.integer(saves)) |>
    mutate(team = schoolfull) %>%
    mutate(overtime = gsub(")", "", overtime)) |>
    select(date, team, opponent, home_away, home_score, visitor_score, overtime, everything()) %>%
    clean_names() %>%
    mutate_at(vars(-date, -opponent, -home_away, -team), ~str_replace(., "/", "")) %>%
    mutate_at(vars(-date, -team, -opponent, -home_away, -overtime, -g_min), as.numeric) |>
    mutate(home_score = as.integer(home_score), visitor_score = as.integer(visitor_score))


  g_teamside <- g_matches %>% filter(opponent != "Defensive Totals")
  g_opponentside <- g_matches %>% filter(opponent == "Defensive Totals") %>% select(-opponent, -home_away) %>% rename_with(.cols = 6:8, function(x){paste0("defensive_", x)})

  g_joinedmatches <- inner_join(g_teamside, g_opponentside, by = c("date", "team", "home_score", "visitor_score", "overtime"))

  all_joined_matches <- joinedmatches |> inner_join(g_joinedmatches, by = c("date", "team", "opponent", "home_away", "home_score", "visitor_score", "overtime"))

  tryCatch(matchstatstibble <- bind_rows(matchstatstibble, all_joined_matches),
           error = function(e){NA})

  Sys.sleep(2)
}


matchstatstibble <- matchstatstibble %>%
  rename("Date" = "date") %>%
  rename("Team" = "team") %>%
  rename("Opponent" = "opponent") %>%
  rename("Home / Away" = "home_away") %>%
  rename("Result" = "result") %>%
  rename("Home Score" = "home_score") %>%
  rename("Visitor Score" = "visitor_score") %>%
  rename("Overtime" = "overtime") %>%
  rename("Home Goals" = "goals") %>%
  rename("Home Assists" = "assists") %>%
  rename("Home Points" = "points") %>%
  rename("Home Shots" = "shots") %>%
  rename("Home Shots on Goal" = "sog") %>%
#  rename("Home Man Up Goals" = "man_up_g") %>%
#  rename("Home Man Down Goals" = "man_down_g") %>%
  rename("Home Ground Balls" = "gb") %>%
  rename("Home Turnovers" = "to") %>%
  rename("Home Caused Turnovers" = "ct") %>%
  rename("Home Faceoffs Won" = "fo_won") %>%
  rename("Home Faceoffs Taken" = "f_os_taken") %>%
#  rename("Home Penalties" = "pen") %>%
#  rename("Home Penalty Time" = "pen_time") %>%
  rename("Home Goals Allowed" = "goals_allowed") %>%
  rename("Home Saves" = "saves") %>%
#  rename("Home Successful Clears" = "clears") %>%
#  rename("Home Clear Attempts" = "att.x") %>%
#  rename("Home Clear Percentage" = "clear_pct.x") %>%
#  rename("Home OT Goals" = "otg.x") %>%
  rename("Away Goals" = "defensive_goals") %>%
  rename("Away Assists" = "defensive_assists") %>%
  rename("Away Points" = "defensive_points") %>%
  rename("Away Shots" = "defensive_shots") %>%
  rename("Away Shots on Goal" = "defensive_sog") %>%
#  rename("Away Man Up Goals" = "defensive_man_up_g") %>%
#  rename("Away Man Down Goals" = "defensive_man_down_g") %>%
  rename("Away Groundball's" = "defensive_gb") %>%
  rename("Away  Turnovers" = "defensive_to") %>%
  rename("Away  Caused Turnovers" = "defensive_ct") %>%
  rename("Away  Faceoffs Taken" = "defensive_f_os_taken") %>%
  rename("Away  Faceoffs Won" = "defensive_fo_won") |>
#  rename("Away Penalties" = "defensive_pen") %>%
#  rename("Away Penalty Time" = "defensive_pen_time") %>%
  rename("Away Goals Allowed" = "defensive_goals_allowed") %>%
  rename("Away Saves" = "defensive_saves") %>%
#  rename("Away Successful Clears" = "defensive_clears") %>%
#  rename("Away Clear Attempts" = "att.y") %>%
#  rename("Away Clear Percentage" = "clear_pct.y") %>%
#  rename("Away OT Goals" = "otg.y")

  matchstatstibble <- select(matchstatstibble, -c(g, g_min, defensive_g, defensive_g_min))


write_csv(matchstatstibble, matchstatsfilename)

