library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_womens_soccer_teamurls_2019.csv") %>% pull(3)

season = "2019"

root_url <- "https://stats.ncaa.org"

matchstatstibble = tibble()

matchstatsfilename <- paste0("data/ncaa_womens_soccer_matchstats_", season, ".csv")

for (i in urls){
  
  schoolpage <- i %>% read_html()
  
  schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  
  matches <- schoolpage %>% html_nodes(xpath = '//*[@id="game_breakdown_div"]/table') %>% html_table(fill=TRUE)
  
  matches <- matches[[1]] %>% slice(3:n()) %>% row_to_names(row_number = 1) %>% clean_names() %>% remove_empty(which = c("cols")) %>% mutate_all(na_if,"") %>% fill(c(date, result)) %>% mutate_at(vars(5:26),  replace_na, '0') %>% mutate(date = mdy(date), home_away = case_when(grepl("@",opponent) ~ "Away", TRUE ~ "Home"), opponent = gsub("@ ","",opponent), WinLoss = case_when(grepl("L", result) ~ "Loss", grepl("W", result) ~ "Win", grepl("T", result) ~ "Draw"), result = gsub("L ", "", result), result = gsub("W ", "", result), result = gsub("T ", "", result)) %>% separate(result, into=c("score", "overtime"), sep = " \\(") %>% separate(score, into=c("visitor_score", "home_score")) %>% rename(result = WinLoss) %>% mutate(team = schoolfull) %>% mutate(overtime = gsub(")", "", overtime)) %>% select(date, team, opponent, home_away, result, home_score, visitor_score, overtime, everything()) %>% clean_names() %>% mutate_at(vars(-date, -opponent, -home_away, -result, -team), ~str_replace(., "/", "")) %>% mutate_at(vars(-date, -team, -opponent, -home_away, -result, -overtime, -goalie_min_plyd), as.numeric)
  
  teamside <- matches %>% filter(opponent != "Defensive Totals")
  
  opponentside <- matches %>% filter(opponent == "Defensive Totals") %>% select(-opponent, -home_away) %>% rename_with(.cols = 8:29, function(x){paste0("defensive_", x)})
  
  joinedmatches <- inner_join(teamside, opponentside, by = c("date", "team", "result", "home_score", "visitor_score", "overtime", "games"))
  
  tryCatch(matchstatstibble <- bind_rows(matchstatstibble, joinedmatches),
           error = function(e){NA})
  
  message <- paste0("Adding ", schoolfull)
  
  print(message)
  
  Sys.sleep(2)
}

write_csv(matchstatstibble, matchstatsfilename)
