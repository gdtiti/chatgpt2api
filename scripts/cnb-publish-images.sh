#!/bin/sh
set -eu

IMAGE_NAME="${IMAGE_NAME:-chatgpt2api}"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-gdttiti}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-${IMAGE_NAMESPACE}/${IMAGE_NAME}}"
EXTERNAL_REGISTRIES="${EXTERNAL_REGISTRIES:-docker.10fu.com dockerhub.10fu.com}"
EXTERNAL_REGISTRIES_REQUIRED="${EXTERNAL_REGISTRIES_REQUIRED:-0}"
ARCHES="${ARCHES:-amd64 arm64}"
BUILD_CONTEXT="${BUILD_CONTEXT:-.}"
BUILD_TARGET="${BUILD_TARGET:-app}"
ACTIVE_EXTERNAL_REGISTRIES=""

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

skopeo_cmd() {
    if [ "${CNB_DRY_RUN:-}" = "1" ]; then
        printf 'skopeo'
        for arg in "$@"; do
            printf ' %s' "$arg"
        done
        printf '\n'
    else
        skopeo "$@"
    fi
}

ensure_skopeo() {
    if [ "${CNB_DRY_RUN:-}" = "1" ] || command -v skopeo >/dev/null 2>&1; then
        return
    fi
    if command -v apk >/dev/null 2>&1; then
        apk add --no-cache skopeo
        return
    fi
    echo "skopeo is required for multi-registry copy, but no supported package manager was found" >&2
    exit 1
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

append_word() {
    current="$1"
    item="$2"
    if [ -z "$current" ]; then
        printf '%s' "$item"
    else
        printf '%s %s' "$current" "$item"
    fi
}

is_truthy() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

is_tag_build() {
    [ "${CNB_EVENT:-}" = "tag_push" ] || [ "${CNB_BRANCH_TYPE:-}" = "tag" ]
}

base_tags() {
    if is_tag_build; then
        raw_tag="$(sanitize_tag "${CNB_BRANCH:-${CNB_TAG:-release}}")"
        commit_short="$(sanitize_tag "${CNB_COMMIT_SHORT:-${CNB_COMMIT:-manual}}")"
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
            unique_words "$raw_tag" "$version" "$major_minor" "$commit_short"
        else
            unique_words "$raw_tag" "$version" "$commit_short"
        fi
    else
        branch="$(sanitize_tag "${CNB_BRANCH:-main}")"
        commit_short="$(sanitize_tag "${CNB_COMMIT_SHORT:-${CNB_COMMIT:-manual}}")"
        unique_words "latest" "$branch" "$commit_short"
    fi
}

tags_for_arch() {
    arch="$1"
    for tag in $(base_tags); do
        printf '%s-%s\n' "$tag" "$arch"
    done
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
        *) return 1 ;;
    esac
}

registry_password_var() {
    case "$1" in
        docker.10fu.com) printf '%s' "DOCKER_10FU_PASSWORD" ;;
        dockerhub.10fu.com) printf '%s' "DOCKERHUB_10FU_PASSWORD" ;;
        *) return 1 ;;
    esac
}

login_skopeo_registry() {
    registry="$1"
    username="$2"
    password="$3"
    if [ "${CNB_DRY_RUN:-}" = "1" ]; then
        skopeo_cmd login "$registry" -u "$username" --password-stdin
    else
        printf '%s' "$password" | skopeo_cmd login "$registry" -u "$username" --password-stdin
    fi
}

mark_skipped_registry() {
    registry="$1"
    reason="$2"
    message="Skipping mirror registry ${registry}: ${reason}"
    if is_truthy "$EXTERNAL_REGISTRIES_REQUIRED"; then
        echo "$message" >&2
        exit 1
    fi
    echo "$message"
}

prepare_external_registries() {
    for registry in $EXTERNAL_REGISTRIES; do
        if ! username_var="$(registry_username_var "$registry")" || ! password_var="$(registry_password_var "$registry")"; then
            mark_skipped_registry "$registry" "no credential variable mapping"
            continue
        fi
        eval "username=\${$username_var:-}"
        eval "password=\${$password_var:-}"
        if [ -z "$username" ] || [ -z "$password" ]; then
            echo "Using anonymous mirror access for ${registry}; set ${username_var} and ${password_var} to enable login."
        else
            login_skopeo_registry "$registry" "$username" "$password"
        fi
        ACTIVE_EXTERNAL_REGISTRIES="$(append_word "$ACTIVE_EXTERNAL_REGISTRIES" "$registry")"
    done
}

copy_tag_to_mirrors() {
    tag="$1"
    source_image="$2"
    for registry in $ACTIVE_EXTERNAL_REGISTRIES; do
        mirror_image="${registry}/${IMAGE_REPOSITORY}"
        echo "Syncing ${source_image}:${tag} -> ${mirror_image}:${tag}"
        skopeo_cmd copy --all --insecure-policy "docker://${source_image}:${tag}" "docker://${mirror_image}:${tag}"
    done
}

print_summary_for_image() {
    label="$1"
    image="$2"
    echo "[$label] $image"
    echo "  [multi-arch]"
    for tag in $(base_tags); do
        echo "    - ${image}:${tag}"
    done
    for arch in $ARCHES; do
        echo "  [${arch} only]"
        for tag in $(tags_for_arch "$arch"); do
            echo "    - ${image}:${tag}"
        done
    done
}

print_publish_summary() {
    source_image="$1"
    echo "===== CNB Image Publish Summary ====="
    print_summary_for_image "CNB Artifact" "$source_image"
    for registry in $ACTIVE_EXTERNAL_REGISTRIES; do
        print_summary_for_image "Mirror" "${registry}/${IMAGE_REPOSITORY}"
    done
    echo "====================================="
}

required_env CNB_DOCKER_REGISTRY
required_env CNB_REPO_SLUG_LOWERCASE
required_env CNB_TOKEN_USER_NAME
required_env CNB_TOKEN

SOURCE_IMAGE="${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}"

if [ "${CNB_DRY_RUN:-}" = "1" ]; then
    docker_cmd login "$CNB_DOCKER_REGISTRY" -u "$CNB_TOKEN_USER_NAME" --password-stdin
else
    printf '%s' "$CNB_TOKEN" | docker_cmd login "$CNB_DOCKER_REGISTRY" -u "$CNB_TOKEN_USER_NAME" --password-stdin
fi

prepare_external_registries

if [ -n "$ACTIVE_EXTERNAL_REGISTRIES" ]; then
    ensure_skopeo
    login_skopeo_registry "$CNB_DOCKER_REGISTRY" "$CNB_TOKEN_USER_NAME" "$CNB_TOKEN"
else
    echo "No external mirror registries are active; only CNB Artifact will be published."
fi

multi_arch_platforms=""
for arch in $ARCHES; do
    platform="$(platform_for_arch "$arch")"
    if [ -z "$multi_arch_platforms" ]; then
        multi_arch_platforms="$platform"
    else
        multi_arch_platforms="${multi_arch_platforms},${platform}"
    fi
done

multi_arch_tag_args=""
for tag in $(base_tags); do
    multi_arch_tag_args="${multi_arch_tag_args} -t ${SOURCE_IMAGE}:${tag}"
done

echo "Building and pushing multi-arch image tags for ${multi_arch_platforms}:"
for tag in $(base_tags); do
    echo "  - ${tag}"
done

# shellcheck disable=SC2086
docker_cmd buildx build \
    --platform "$multi_arch_platforms" \
    --target "$BUILD_TARGET" \
    --push \
    $multi_arch_tag_args \
    "$BUILD_CONTEXT"

for tag in $(base_tags); do
    copy_tag_to_mirrors "$tag" "$SOURCE_IMAGE"
done

for arch in $ARCHES; do
    platform="$(platform_for_arch "$arch")"
    tag_args=""

    for tag in $(tags_for_arch "$arch"); do
        tag_args="${tag_args} -t ${SOURCE_IMAGE}:${tag}"
    done

    echo "Building and pushing ${platform} image tags:"
    for tag in $(tags_for_arch "$arch"); do
        echo "  - ${tag}"
    done

    # shellcheck disable=SC2086
    docker_cmd buildx build \
        --platform "$platform" \
        --target "$BUILD_TARGET" \
        --push \
        $tag_args \
        "$BUILD_CONTEXT"

    for tag in $(tags_for_arch "$arch"); do
        copy_tag_to_mirrors "$tag" "$SOURCE_IMAGE"
    done
done

print_publish_summary "$SOURCE_IMAGE"
