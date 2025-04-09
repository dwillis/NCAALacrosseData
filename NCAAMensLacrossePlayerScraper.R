library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_mens_lacrosse_teamurls_2025.csv") %>% pull(2)
season = "2025"

root_url <- "https://stats.ncaa.org"
playerstatstibble = tibble()

playerstatsfilename <- paste0("data/ncaa_mens_lacrosse_playerstats_", season, ".csv")

for (i in urls){

  schoolpage <- i %>% read_html()

  if (i == "https://stats.ncaa.org/team/282/stats/15203") { # special case for Hobart in 2019-20
    schoolfull = 'Hobart Statesmen'
  } else {
    schoolfull <- schoolpage |> html_nodes(xpath = '/html/body/div[2]/div/div/div/div/div/div[1]/img') |> html_attr('alt')
#    schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  }

  player_ids <- schoolpage %>% html_nodes(xpath = '//*[@id="stat_grid"]') %>% html_nodes("a") %>% html_attr("href") %>% as_tibble() %>% rename(path = value)

  player_ids <- player_ids %>% mutate(ncaa_id = str_extract(path, "\\d+"))

  playerstats <- schoolpage %>% html_nodes(xpath = '//*[@id="stat_grid"]') %>% html_table()

  playerstats <- playerstats[[1]]

  playerstats <- playerstats %>% clean_names() %>% filter(player != "TEAM" & player != "Totals" & player != "Opponent Totals") %>% mutate(roster_name = player, jersey = number, full_name = player) %>% separate(player, into=c("first_name", "last_name"), sep=" ")

  playerstats <- playerstats %>% mutate(first_name = str_trim(first_name)) %>% mutate(team = schoolfull, season = season) %>% select(season, team, jersey, full_name, roster_name, first_name, last_name, yr, pos, everything()) %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), ~str_replace(., ",", "")) %>%  mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), as.numeric)

  playerstats <- cbind(playerstats, ncaa_id = player_ids$ncaa_id)

  playerstats <- replace(playerstats, is.na(playerstats), 0)

  message <- paste0("Fetching ", schoolfull)

  playerstats <- playerstats %>%
   rename("Season" = "season") %>%
   rename("Jersey Number" = "number") %>%
   rename("Team" = "team") %>%
   rename("Full Name" = "full_name") %>%
   rename("Roster Name" = "roster_name") %>%
   rename("First Name" = "first_name") %>%
   rename("Last Name" = "last_name") %>%
   rename("Year" = "yr") %>%
   rename("Position" = "pos") %>%
   rename("Games Played" = "gp") %>%
   rename("Games Started" = "gs") %>%
#   rename("g" = "g") %>%
#   rename("gs_2" = "gs_2") %>%
   rename("Goals" = "goals") %>%
   rename("Assists" = "assists") %>%
   rename("Points" = "points") %>%
   rename("Shots" = "shots") %>%
#   rename("Shooting Percentage" = "shot_pct") %>%
   rename("Shots on Goal" = "sog") %>%
#   rename("Shots on Goal Percentage" = "sog_pct") %>%
#   rename("Game Winning Goals" = "gwg") %>%
#   rename("Powerplay Goals" = "man_up_g") %>%
#   rename("Penalty Kill Goals" = "man_down_g") %>%
   rename("Ground Balls" = "gb") %>%
   rename("Turnovers" = "to") %>%
   rename("Caused Turnovers" = "ct") %>%
   rename("Faceoffs Won" = "fo_won") %>%
   rename("Faceoffs Taken" = "f_os_taken") %>%
#   rename("Faceoff Percentage" = "fo_pct") %>%
#   rename("Penalties" = "pen_time") %>%
#   rename("Goalie Games Played" = "ggp") %>%
#   rename("Goalie Games Started" = "ggs") %>%
#   rename("Goalie Minutes" = "g_min") %>%
#   rename("Goals Allowed" = "goals_allowed") %>%
#   rename("GAA" = "gaa") %>%
#   rename("Saves" = "saves") %>%
#   rename("Save Percentage" = "save_pct") %>%
   rename("NCAA id" = "ncaa_id")

  print(message)

  tryCatch(playerstatstibble <- bind_rows(playerstatstibble, playerstats),
           error = function(e){NA})

  Sys.sleep(2)
}

playerstatstibble <- playerstatstibble %>% remove_empty(which="rows")

write_csv(playerstatstibble, playerstatsfilename)
