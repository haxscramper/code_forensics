SELECT tmp.name AS author_name,
       commits.period AS sample_period,
       sum(tmp.lines) AS lines
  FROM (
        SELECT author.name AS name,
               file_lines.file AS FILE,
               count(author.id) AS lines
          FROM file_lines
         INNER JOIN LINE
            ON file_lines.line = line.id
         INNER JOIN commits
            ON line.rcommit = commits.id
         INNER JOIN author
            ON commits.author == author.id
         GROUP BY name,
                  FILE
         ORDER BY lines DESC
       ) AS tmp
 INNER JOIN FILE
    ON tmp.file = file.id
 INNER JOIN commits
    ON file.rcommit = commits.id
 GROUP BY author_name,
          sample_period
 ORDER BY author_name ASC,
          sample_period DESC;
