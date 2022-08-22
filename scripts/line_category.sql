CREATE VIEW commit_file_lines (commit_time, file_path, file_id, line_id, file_parent) AS SELECT rcommit.time AS commit_time,
       (dir.name || strings.text) AS file_path,
       file.parent AS file_parent,
       file_lines.file AS file_id,
       file_lines.line AS line_id
  FROM file_lines
 INNER JOIN LINE
    ON file_lines.line = line.id
 INNER JOIN rcommit
    ON file.rcommit = rcommit.id
 INNER JOIN FILE
    ON file_lines.file = file.id
 INNER JOIN dir
    ON file.parent = dir.id
 INNER JOIN strings
    ON file.name = strings.id;
