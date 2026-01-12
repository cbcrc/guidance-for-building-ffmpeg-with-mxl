# shellcheck shell=bash
# Usage: source "$SCRIPT_DIR"/module/read_list.sh

: "${SCRIPT_DIR:?SCRIPT_DIR not set}"
# shellcheck source=./module/logging.sh
source "${SCRIPT_DIR}"/module/logging.sh

# _require_declared_empty_array <array-name>
#
# Fails unless <array-name> refers to a declared array that is empty.
_require_declared_empty_array() {
    local array_name="$1"

    # valid variable name
    if [[ ! "$array_name" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
        log_error "invalid variable name: $array_name"
        exit 1
    fi

    # fail if the target variable is undeclared
    if ! declare -p "$array_name" >/dev/null 2>&1; then
        log_error "target variable is undeclared: $array_name"
        exit 1
    fi

    # fail if the target variable is non-empty
    if eval '(( ${#'"$array_name"'[@]} ))' >/dev/null 2>&1; then
        log_error "target variable already populated: $array_name"
        exit 1
    fi
}


# read_one_list <array-name> <file>
#
# Reads a list of items from a file into the named array.
#   - one item per line
#   - blank lines ignored
#   - lines starting with '#' ignored
#   - trailing comments allowed after whitespace
#
# Example:
#   local -a apt_pkgs
#   read_one_list apt_pkgs apt-dependencies.txt
#   apt-get install -y --no-install-recommends "${apt_pkgs[@]}"
read_one_list() {
    local array_name="$1"
    local file="${SCRIPT_DIR}/$2"
    
    if [[ ! -f "$file" ]]; then
        log_error "read_one_list: file not found: $file"
        exit 1
    fi

    _require_declared_empty_array "$array_name"

    local -a tmp=()
    local line

    while IFS= read -r line; do
        tmp+=("$line")
    done < <(
        grep -Ev '^\s*(#|$)' "$file" |
        sed 's/\s\+#.*$//'
    )

    eval "$array_name"='("${tmp[@]}")'
}

# read_list <array-name> <list-file>...
#
# For each <list-file>, read its lines using read_one_list semantics
# (one item per line, blank lines and comments ignored), and append
# all items to the named array in the order the files are given.
#
# Example:
#   local -a options
#   read_list options base_options extra_options
#   configure "${options[@]}"
read_list() {
    local array_name="$1"
    shift

    if [[ $# -lt 1 ]]; then
        log_error "read_list: no list files specified"
        exit 1
    fi

    _require_declared_empty_array "$array_name"

    local list_file
    local -a tmp=()

    for list_file in "$@"; do
        local -a part=()
        read_one_list part "$list_file" || exit 1
        tmp+=( "${part[@]}" )
    done

    eval "$array_name"='("${tmp[@]}")'
}
