CREATE VIEW commit_file_lines (commit_id, file_path, file_id, line_id) AS SELECT rcommit.id AS commit_id,
       strings.text AS file_path,
       file_lines.file AS file_id,
       file_lines.line AS line_id
  FROM file_lines
 INNER JOIN LINE
    ON file_lines.line = line.id
 INNER JOIN rcommit
    ON line.rcommit = rcommit.id
 INNER JOIN FILE
    ON file_lines.file = file.id
 INNER JOIN strings
    ON file.name = strings.id;--
