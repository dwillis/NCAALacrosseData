library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_mens_lacrosse_teamurls_2023.csv") %>% pull(3)

season = "2023"

root_url <- "https://stats.ncaa.org"

matchstatstibble = tibble()

matchstatsfilename <- paste0("data/ncaa_mens_lacrosse_matchstats_", season, ".csv")

for (i in urls){
  
  schoolpage <- i %>% read_html()
  
  if (str_detect(i, "org_id=282")) { # special case for Hobart
    schoolfull = 'Hobart Statesmen'
  } else {
    schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  }
  
  message <- paste0("Adding ", schoolfull)
  
  print(message)
  
  schoolpage %>% html_nodes(xpath = '/html/body/div[2]/fieldset[1]/legend/a[1]') %>% html_text()
  
  matches <- schoolpage %>% html_nodes(xpath = '//*[@id="game_breakdown_div"]/table') %>% html_table()
  
  # doesn't handle postponed games right now (Hobart has one)
  # doesn't retain W/L, need to calculate that from score.

  matches <- matches[[1]] %>% slice(3:n()) %>% row_to_names(row_number = 1) %>% clean_names() %>% 
    remove_empty(which = c("cols")) %>% 
    mutate_all(na_if,"") %>% 
    fill(c(date, result)) %>% 
    mutate_at(vars(5:26),  replace_na, '0') %>% 
    mutate(date = mdy(date), home_away = case_when(grepl("@",opponent) ~ "Away", TRUE ~ "Home"), opponent = gsub("@ ","",opponent)) %>%
#    mutate(WinLoss = case_when(grepl("L", result) ~ "Loss", grepl("W", result) ~ "Win", grepl("T", result) ~ "Draw"), 
#           result = gsub("L ", "", result), result = gsub("W ", "", result), result = gsub("T ", "", result)) %>% 
    separate(result, into=c("score", "overtime"), sep = " \\(") %>% 
    separate(score, into=c("home_score", "visitor_score")) %>% 
#    rename(result = WinLoss) %>% 
    mutate(result = is.character(NA)) %>% # placeholder for now
    mutate(team = schoolfull) %>% 
    mutate(overtime = gsub(")", "", overtime)) %>% 
    select(date, team, opponent, home_away, result, home_score, visitor_score, overtime, everything()) %>% 
    clean_names() %>% 
    mutate_at(vars(-date, -opponent, -home_away, -result, -team), ~str_replace(., "/", "")) %>% 
    mutate_at(vars(-date, -team, -opponent, -home_away, -result, -overtime, -g_min), as.numeric)
  
  teamside <- matches %>% filter(opponent != "Defensive Totals")
  
  opponentside <- matches %>% filter(opponent == "Defensive Totals") %>% select(-opponent, -home_away) %>% rename_with(.cols = 7:30, function(x){paste0("defensive_", x)})
  
  joinedmatches <- inner_join(teamside, opponentside, by = c("date", "team", "result", "home_score", "visitor_score", "overtime"))
  
  tryCatch(matchstatstibble <- bind_rows(matchstatstibble, joinedmatches),
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
  rename("Home Man Up Goals" = "man_up_g") %>%
  rename("Home Man Down Goals" = "man_down_g") %>% 
  rename("Home Ground Balls" = "gb") %>% 
  rename("Home Turnovers" = "to") %>% 
  rename("Home Caused Turnovers" = "ct") %>% 
  rename("Home Faceoffs Won" = "fo_won") %>% 
  rename("Home Faceoffs Taken" = "f_os_taken") %>%
  rename("Home Penalties" = "pen") %>% 
  rename("Home Penalty Time" = "pen_time") %>% 
  rename("Home Goals Allowed" = "goals_allowed") %>%
  rename("Home Saves" = "saves") %>% 
  rename("Home Successful Clears" = "clears") %>%
  rename("Home Clear Attempts" = "att.x") %>% 
  rename("Home Clear Percentage" = "clear_pct.x") %>% 
  rename("Home OT Goals" = "otg.x") %>% 
  rename("Away Goals" = "defensive_goals") %>% 
  rename("Away Assists" = "defensive_assists") %>% 
  rename("Away Points" = "defensive_points") %>% 
  rename("Away Shots" = "defensive_shots") %>%
  rename("Away Shots on Goal" = "defensive_sog") %>%
  rename("Away Man Up Goals" = "defensive_man_up_g") %>% 
  rename("Away Man Down Goals" = "defensive_man_down_g") %>% 
  rename("Away Groundball's" = "defensive_gb") %>%
  rename("Away  Turnovers" = "defensive_to") %>%
  rename("Away  Caused Turnovers" = "defensive_ct") %>%
  rename("Away  Faceoffs Taken" = "defensive_f_os_taken") %>%
  rename("Away  Faceoffs Won" = "defensive_fo_won") %>% 
  rename("Away Penalties" = "defensive_pen") %>%
  rename("Away Penalty Time" = "defensive_pen_time") %>%
  rename("Away Goals Allowed" = "defensive_goals_allowed") %>%
  rename("Away Saves" = "defensive_saves") %>%
  rename("Away Successful Clears" = "defensive_clears") %>%
  rename("Away Clear Attempts" = "att.y") %>%
  rename("Away Clear Percentage" = "clear_pct.y") %>%
  rename("Away OT Goals" = "otg.y") 
  
  
  matchstatstibble <- select(matchstatstibble, -c(g, g_min, w, l, t, rc, yc, defensive_g, defensive_w, defensive_l, defensive_t, defensive_rc, defensive_yc, defensive_g_min))
  

write_csv(matchstatstibble, matchstatsfilename)

