#!/bin/sh
set -eu

IMAGE_NAME="${IMAGE_NAME:-chatgpt2api}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-gdttiti}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-${IMAGE_NAMESPACE}/${IMAGE_NAME}}"
EXTERNAL_REGISTRIES="${EXTERNAL_REGISTRIES:-docker.10fu.com dockerhub.10fu.com}"
ARCHES="${ARCHES:-amd64 arm64}"

required_env() {
    name="$1"
    eval "value=\${$name:-}"
    if [ -z "$value" ]; then
        echo "Missing required environment variable: $name" >&2
        exit 1
    fi
}

docker_cmd() {
    if [ "${CNB_DRY_RUN:-}" = "1" ]; then
        printf 'docker'
        for arg in "$@"; do
            printf ' %s' "$arg"
        done
        printf '\n'
    else
        docker "$@"
    fi
}

sanitize_tag() {
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's#[^a-z0-9_.-]+#-#g; s#^-+##; s#-+$##'
}

unique_words() {
    seen=" "
    for item in "$@"; do
        if [ -n "$item" ] && ! printf '%s' "$seen" | grep -q " $item "; then
            printf '%s\n' "$item"
            seen="${seen}${item} "
        fi
    done
}

is_tag_build() {
    [ "${CNB_EVENT:-}" = "tag_push" ] || [ "${CNB_BRANCH_TYPE:-}" = "tag" ]
}

tags_for_arch() {
    arch="$1"
    if is_tag_build; then
        raw_tag="$(sanitize_tag "${CNB_BRANCH:-${CNB_TAG:-release}}")"
        version="${raw_tag#v}"
        major_minor=""
        case "$version" in
            [0-9]*.[0-9]*.[0-9]*)
                major="$(printf '%s' "$version" | cut -d. -f1)"
                minor="$(printf '%s' "$version" | cut -d. -f2)"
                major_minor="${major}.${minor}"
                ;;
        esac
        if [ -n "$major_minor" ]; then
            unique_words "${raw_tag}-${arch}" "${version}-${arch}" "${major_minor}-${arch}"
        else
            unique_words "${raw_tag}-${arch}" "${version}-${arch}"
        fi
    else
        branch="$(sanitize_tag "${CNB_BRANCH:-main}")"
        commit_short="$(sanitize_tag "${CNB_COMMIT_SHORT:-${CNB_COMMIT:-manual}}")"
        unique_words "latest-${arch}" "${branch}-${arch}" "${commit_short}-${arch}"
    fi
}

platform_for_arch() {
    case "$1" in
        amd64) printf '%s' "linux/amd64" ;;
        arm64|arm) printf '%s' "linux/arm64" ;;
        *)
            echo "Unsupported architecture: $1" >&2
            exit 1
            ;;
    esac
}

registry_username_var() {
    case "$1" in
        docker.10fu.com) printf '%s' "DOCKER_10FU_USERNAME" ;;
        dockerhub.10fu.com) printf '%s' "DOCKERHUB_10FU_USERNAME" ;;
        *)
            echo "No credential variable mapping for registry: $1" >&2
            exit 1
            ;;
    esac
}

registry_password_var() {
    case "$1" in
        docker.10fu.com) printf '%s' "DOCKER_10FU_PASSWORD" ;;
        dockerhub.10fu.com) printf '%s' "DOCKERHUB_10FU_PASSWORD" ;;
        *)
            echo "No credential variable mapping for registry: $1" >&2
            exit 1
            ;;
    esac
}

login_registry() {
    registry="$1"
    username_var="$(registry_username_var "$registry")"
    password_var="$(registry_password_var "$registry")"
    required_env "$username_var"
    required_env "$password_var"
    eval "username=\${$username_var}"
    eval "password=\${$password_var}"
    if [ "${CNB_DRY_RUN:-}" = "1" ]; then
        docker_cmd login "$registry" -u "$username" --password-stdin
    else
        printf '%s' "$password" | docker_cmd login "$registry" -u "$username" --password-stdin
    fi
}

required_env CNB_DOCKER_REGISTRY
required_env CNB_REPO_SLUG_LOWERCASE
required_env CNB_TOKEN_USER_NAME
required_env CNB_TOKEN

if [ "${CNB_DRY_RUN:-}" = "1" ]; then
    docker_cmd login "$CNB_DOCKER_REGISTRY" -u "$CNB_TOKEN_USER_NAME" --password-stdin
else
    printf '%s' "$CNB_TOKEN" | docker_cmd login "$CNB_DOCKER_REGISTRY" -u "$CNB_TOKEN_USER_NAME" --password-stdin
fi

for registry in $EXTERNAL_REGISTRIES; do
    login_registry "$registry"
done

for arch in $ARCHES; do
    platform="$(platform_for_arch "$arch")"
    tag_args=""

    for tag in $(tags_for_arch "$arch"); do
        tag_args="${tag_args} -t ${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:${tag}"
        for registry in $EXTERNAL_REGISTRIES; do
            tag_args="${tag_args} -t ${registry}/${IMAGE_REPOSITORY}:${tag}"
        done
    done

    echo "Building and pushing ${platform} image tags:"
    for tag in $(tags_for_arch "$arch"); do
        echo "  - ${tag}"
    done

    # shellcheck disable=SC2086
    docker_cmd buildx build \
        --platform "$platform" \
        --target app \
        --push \
        $tag_args \
        .
done
