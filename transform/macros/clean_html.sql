{#
    Turn a job description into plain text.

    Greenhouse returns the description double-encoded: HTML tags arrive as
    `&lt;div&gt;` rather than `<div>`. So entities must be decoded *before*
    tags can be stripped. `&amp;` is decoded last — decoding it first would
    turn `&amp;lt;` into `<` and corrupt any literal entity in the text.
#}
{% macro clean_html(column) %}
    nullif(
        trim(
            regexp_replace(
                regexp_replace(
                    replace(
                        replace(
                            replace(
                                replace(
                                    replace(
                                        replace({{ column }}, '&lt;', '<'),
                                    '&gt;', '>'),
                                '&quot;', '"'),
                            '&#39;', ''''),
                        '&nbsp;', ' '),
                    '&amp;', '&'),
                '<[^>]*>', ' ', 'g'),
            '\s+', ' ', 'g')
        ),
        ''
    )
{% endmacro %}
