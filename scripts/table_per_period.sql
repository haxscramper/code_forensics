SELECT rcommit.period AS sample_period,
       tmp.commit_period AS commit_period,
       sum(tmp.lines) AS lines,
       tmp.commit_hash AS hash
  FROM (
        SELECT rcommit.period AS commit_period,
               rcommit.hash AS commit_hash,
               file_lines.file AS FILE,
               count(file_lines.line) AS lines
          FROM file_lines
         INNER JOIN LINE
            ON file_lines.line = line.id
         INNER JOIN rcommit
            ON line.rcommit = rcommit.id
         GROUP BY commit_period,
                  FILE
         ORDER BY lines DESC
       ) AS tmp
 INNER JOIN FILE
    ON tmp.file = file.id
 INNER JOIN rcommit
    ON file.rcommit = rcommit.id
 GROUP BY commit_period,
          sample_period
 ORDER BY commit_period ASC,
          sample_period DESC;
