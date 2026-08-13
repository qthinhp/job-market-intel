{#
    dbt's default behaviour prefixes custom schemas with the target schema,
    producing `main_marts`. Overriding it gives clean `staging` / `marts`
    schemas, which matters here because Power BI users browse these names.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
