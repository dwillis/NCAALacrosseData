# NCAA Lacrosse Data

A repository of men's and women's lacrosse data scraped from stats.ncaa.org, plus the scrapers that did the work.

The guiding principals of this scrape were really centered on two goals: to create a database that includes every player in the country, and to give users to opportunity to sort and filter. NCAA stats are generally speaking pretty well kept. There certainly are exceptions to that rule, but for the most part the stats are well kept. The problem is that the stats live on separate school websites, usually in different formats. 

The website stats.ncaa.org does a great job of tracking every school and player, but does not give users the opportunity to compare players across the country. Our challenge was to take the data that existed on the website in predictable (repeatable) urls and pull it into a larger database. 

That is the one strong value of the NCAA website. It is so predictable that we were able to adapt our code from NCAA soccer data. With relatively minor changes and updating url’s, it is relatively easy to adapt similar code across different sports. 


### Scraper Setup

To scrape match and player stats for both men's and women's matches, we first need a canonical list of teams for each season and their NCAA stats urls, derived from [this page](https://stats.ncaa.org/rankings/institution_trends) for each sport. Those CSV files are stored in the `url_csvs` directory, one for each season. There's no simple way to automate building those files, since we need the HTML for urls and the NCAA stats site doesn't have permalinks for each season (it could be automated using a browser emulator such as Selenium, however). But copying and pasting probably works fine for something we need to update only occasionally.

To create the teamurls\_{season}.csv files, grab the HTML source and, using a text editor, isolate the contents of the <table> tag. Save that file as HTML and then open it in Excel. It should look something like this:

![Excel version of HTML table](images/team_html.png "Excel version of HTML table").

What we want is a CSV file with the team name and URLs for player stats and match stats. Both of those follow predictable patterns:

* Player stats URL example: https://stats.ncaa.org/team/5/stats/15840
* Match stats URL example: https://stats.ncaa.org/player/game_by_game?org_id=5&game_sport_year_ctl_id=15840&stats_player_seq=-100

Where `/5/` is the NCAA ID (called org_id in the match stats URL) for a team and `/15840` is the NCAA code for the specific sport and year (called game_sport_year_ctl_id in the match stats URL). For 2023 men's lacrosse the sport and year code is 16320 for all teams. Given a list of teams and their IDs (which we can extract from the HTML links), we can construct those two URLs. That's why we need the HTML - to get the team IDs.

You can remove all of the columns from the Excel version of the HTML file except the one labeled `Institution`, and save it again. Then open the file in a text editor and start removing the HTML you don't need. Find and replace will do. What you want is a comma or tab-separated file with the URL segment (like `/team/721/16320`) and the team name in separate columns. Then you can replace those URL segment with the actual URLs you'll need for the scrapers to work.

### Scraper Details

The four scrapers - two for men's and women's lacrosse - are R scripts, not notebooks, so they can be run in RStudio by highlighting the entire script and clicking the "Run" button or from the command line using `Rscript name_of_file.R`. All scripts iterate over the list of teams for a given year, which you set at the top of the script, and pause for 2 seconds between each team.
  
Using github actions, we were able to fairly easily automate the process of updating the scraper. One value of scraping college lacrosse data is that games are played on predictable days, primarily Saturday, Sunday, and Tuesday. By running the scraper on Sunday, Monday, and Wednesday mornings, it is possible to get an accurate and mostly up to date scraper working without having to pay for more powerful or frequent automations. 
  
## Displaying Results of the Scrape 
  
We ultimately used Datasette to display the results of our scrape, and hosted it using a heroku app. I found Datasette to be incredibly powerful, but it had certain drawbacks. For someone who is extremely curious, and somewhat familiar with data analysis, Datasette was very useful. It provided the basic goal of the scrape which was to be able to sort and filter. The problems with Datasette are that it is not overly compatible with mobile devices, and it can be overwhelming for first time users. 
  
With that in mind, I chose to focus the final weeks of the project on finding ways to visualize the data, to provide some initial insights to a first time or casual user. 
  
We added capability to the datasette app for the user to use the vega and vega-lite applications to make their own charts, but it was difficult to embed custom premade charts. We settled on using vega-lite within Observablehq.com. This provided a good option to handle significant amounts of data, and provide interesting scatter plots and other charts that were also easy to embed in wordpress and other similar sites. 

## Priorities of Scrape 
  
  The app is best at giving the super curious user (for example a lacrosse media member) the tools to follow their own curiosity. It is less successful at showing a casual viewer (or even someone who is not super interested in stats) things they might find interesting. We have attempted to solve this problem by hosting interactive charts on a tangential web page to the datasette. 

However, this dilemma points at a larger question, which is choosing who to market the site towards. 

Non-revenue sports have multiple issues. One is fluency. Will everyone who comes to the site know what every stat abbreviation is? The answer may not always be as simple as it seems, especially if personal social networks (like mine) are disproportionately filled by diehards of the sport. 

The next problem is balancing the interests of casual fans vs those who are very interested in data. Being on the forefront of data collection is exciting and potentially noteworthy, but it is also uphill sledding. If people have never had the data you are providing, they also won’t be adept or prepared to use it. The goal of the data provider should be to create something easy enough to use that beginners can find something useful from it. Datasette is better suited to the super interested observer who has some data fluency, which is something students should consider. 

The third and most important long-term issue is that limited data means limited value of the data. In NCAA lacrosse, the major gap in data comes from not knowing who is on the field at a given time. If we had lineup data, there would be a lot more interesting outcomes. For example, what percentage of the time does a team score with their first midfield line vs their second line? What defensive lineups are the most stingy? 

The point of data analysis is to show who the most impactful players are. Without specific data like this, there are limited outcomes. This is a reality of the data world, but something students should consider. 

## Market for Sites In Non-Revenue Sports
  
This points to broader issues with these websites in general. To properly execute a useful website, it requires a significant amount of time. This often pushes creators into the common dilemma of using a subscription model vs offering the site for free. The problem is that site traffic for up and coming sports is unlikely to be sufficient to create real ad revenue, so a subscription model is a must. However, the lack of diehard fans makes the subscription model a difficult one too. So there are real issues with the creative side of these sites, which are systemic to their non-revenue sports. Simply, not enough people care enough to justify the workload. 

However, there are huge benefits to these sites as well. Two prominent examples are in uncovering unheralded players from unheralded programs, and also in influencing award voting. Promotion for statistical excellence falls mostly on school’s themselves, and those with better or worse resources in their SID departments will have a better chance at getting their players into the popular conscience. These sites can help fans realize who the statistical performers, even if they don’t play on ESPN. 

That same argument holds true for award voting, which has long been greatly impacted by exposure, performance from recent years, and old-fashioned popularity. Making these stats more public will help create a smarter lacrosse consumer, and help build more transparent resumes that can be compared across the country. As an athlete, I experienced both sides of this (struggle to gain exposure and recognition, followed by over-recognition after a transfer) and it matters more than you may realize. Pro careers, resume builders in the transfer portal, an cache in the sport forever are all on the line. 

 ## Limits to overcome in future Analysis 

The main issue with the NCAA stats is that there are small differences in the ways that schools keep their stats, especially when it comes to play by play data. One of the goals that were failed to be accomplished was extracting information from play by play scripts. There are a few reasons why. 

The first is that there was no consistency with the url’s used for pxp data. The division one men’s lacrosse games had unique id’s for pxp data and box score data, and the pxp id’s were not within a specific range, which meant that to extract url’s, the programmer would have to manually catalog the unique url (and game id) for every game across the country. 

The second issue is that there is inconsistency with the ways that athletic departments catalog their games. For example, while Cornell uses the abbreviation “COR” in their pxp data, Hobart uses their full title, “Hobart.” Better yet, schools like Quinnipiac use the abbreviation “QUMLAX23.” Army West Point changes their abbreviation by game. One game they use ‘ARMYM”, another “ARMY”. So while theoretically possible to find individual play by play data and extract it, the messiness of the data make it nearly impossible to decode. Other sports like College Basketball, have their data cleaned by sites like ESPN, which make scraping the data much easier, which is part of the reason why there is so much data. 
