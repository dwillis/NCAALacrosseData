library(tidyverse)
library(lubridate)
library(rvest)
library(janitor)

urls <- read_csv("url_csvs/ncaa_mens_lacrosse_teamurls_2023.csv") %>% pull(2)
season = "2023"

root_url <- "https://stats.ncaa.org"
playerstatstibble = tibble()

playerstatsfilename <- paste0("data/ncaa_mens_lacrosse_playerstats_", season, ".csv")

for (i in urls){
  
  schoolpage <- i %>% read_html()
  
  if (i == "https://stats.ncaa.org/team/282/stats/15203") { # special case for Hobart in 2019-20
    schoolfull = 'Hobart Statesmen'
  } else {
    schoolfull <- schoolpage %>% html_nodes(xpath = '//*[@id="contentarea"]/fieldset[1]/legend/a[1]') %>% html_text()
  }
  
  player_ids <- schoolpage %>% html_nodes(xpath = '//*[@id="stat_grid"]') %>% html_nodes("a") %>% html_attr("href") %>% as_tibble() %>% rename(path = value)
  
  player_ids <- player_ids %>% mutate(ncaa_id = str_split(path, "=", simplify = TRUE)[ , 4])
  
  playerstats <- schoolpage %>% html_nodes(xpath = '//*[@id="stat_grid"]') %>% html_table()
  
  playerstats <- playerstats[[1]]
  
  playerstats <- playerstats %>% clean_names() %>% filter(player != "TEAM" & player != "Totals" & player != "Opponent Totals") %>% mutate(roster_name = player) %>% separate(player, into=c("last_name", "first_name"), sep=",")
  
  playerstats <- playerstats %>% mutate(full_name = str_trim(paste(first_name, last_name, sep=" ")), first_name = str_trim(first_name)) %>% mutate(team = schoolfull, season = season) %>% select(season, team, jersey, full_name, roster_name, first_name, last_name, yr, pos, everything()) %>% mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos), ~str_replace(., ",", "")) %>%  mutate_at(vars(-season, -team, -jersey, -full_name, -roster_name, -first_name, -last_name, -yr, -pos, -ggs, -g_min), as.numeric)
  
  playerstats <- cbind(playerstats, ncaa_id = player_ids$ncaa_id)
  
  message <- paste0("Fetching ", schoolfull)
  
  print(message)
  
  tryCatch(playerstatstibble <- bind_rows(playerstatstibble, playerstats),
           error = function(e){NA})
  
  Sys.sleep(2)
}

select(playerstats, -g, -gs_2, -roster_name, -rc, -yc, -clears, -att, -clear_pct, -otg)

playerstatstibble <- playerstatstibble %>% remove_empty(which="rows")

write_csv(playerstatstibble, playerstatsfilename)