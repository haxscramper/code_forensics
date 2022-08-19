SELECT
  author.`name` as name,
  commits.period AS period,
  count(author.`name`) as lines
from file_lines
inner join line on file_lines.line = line.id
inner join commits on line.`commit` = commits.id
inner join author on commits.author == author.id
group by
  name,
  period
order by
  lines DESC;