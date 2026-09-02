#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <random>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {

constexpr int kLength = 11;
constexpr int kRadius = 3;
constexpr int kAmbient = 1 << kLength;
constexpr int kCodeSize = 15;
constexpr int kBallSize = 232;

using Ball = std::array<int, kBallSize>;
using Code = std::array<int, kCodeSize>;

const std::array<int, 16> kBaseline{
    0, 137, 341, 476, 619, 738, 830, 951,
    1096, 1217, 1309, 1428, 1571, 1706, 1910, 2047,
};

struct Options {
    std::uint64_t iterations = 1000000;
    std::uint64_t restart_iterations = 20000;
    std::uint64_t breakout_stagnation = 250;
    std::uint64_t seed = 1;
    std::string best_code_path;
    std::string summary_path;
    bool self_test = false;
    bool quiet = false;
};

struct Metrics {
    int uncovered = 0;
    int singletons = 0;
    std::uint64_t weighted_uncovered = 0;
};

struct Candidate {
    int remove_position = -1;
    int add_word = -1;
    std::uint64_t weighted_uncovered =
        std::numeric_limits<std::uint64_t>::max();
    int uncovered = std::numeric_limits<int>::max();
    int singletons = std::numeric_limits<int>::max();
    std::uint64_t tie_break = std::numeric_limits<std::uint64_t>::max();
};

std::vector<Ball> build_balls() {
    std::vector<Ball> balls(static_cast<std::size_t>(kAmbient));
    for (int center = 0; center < kAmbient; ++center) {
        int index = 0;
        for (int target = 0; target < kAmbient; ++target) {
            if (std::popcount(
                    static_cast<unsigned int>(center ^ target)
                ) <= kRadius) {
                if (index >= kBallSize) {
                    throw std::logic_error("Hamming ball is too large");
                }
                balls[static_cast<std::size_t>(center)]
                     [static_cast<std::size_t>(index++)] = target;
            }
        }
        if (index != kBallSize) {
            throw std::logic_error("Hamming ball has the wrong size");
        }
    }
    return balls;
}

class State {
  public:
    State(
        Code code,
        const std::vector<Ball>& balls,
        std::vector<std::uint32_t>& weights
    )
        : code_(std::move(code)),
          balls_(balls),
          weights_(weights) {
        position_.fill(-1);
        coverage_mask_.fill(0);
        for (int position = 0; position < kCodeSize; ++position) {
            const int word = code_[static_cast<std::size_t>(position)];
            if (word < 0 || word >= kAmbient) {
                throw std::invalid_argument("codeword is outside the cube");
            }
            if (position_[static_cast<std::size_t>(word)] != -1) {
                throw std::invalid_argument("code contains duplicates");
            }
            position_[static_cast<std::size_t>(word)] = position;
            for (const int target : balls_[static_cast<std::size_t>(word)]) {
                coverage_mask_[static_cast<std::size_t>(target)] |=
                    static_cast<std::uint16_t>(1U << position);
            }
        }
        if (code_[0] != 0) {
            throw std::invalid_argument("the anchored codeword must be zero");
        }
        rebuild_metrics();
    }

    [[nodiscard]] const Code& code() const {
        return code_;
    }

    [[nodiscard]] const Metrics& metrics() const {
        return metrics_;
    }

    [[nodiscard]] bool selected(int word) const {
        return position_[static_cast<std::size_t>(word)] >= 0;
    }

    [[nodiscard]] int choose_uncovered_target(
        std::mt19937_64& rng
    ) const {
        std::uint32_t maximum_weight = 0;
        int choices = 0;
        int selected_target = -1;
        for (int target = 0; target < kAmbient; ++target) {
            if (coverage_mask_[static_cast<std::size_t>(target)] != 0) {
                continue;
            }
            const std::uint32_t weight =
                weights_[static_cast<std::size_t>(target)];
            if (weight > maximum_weight) {
                maximum_weight = weight;
                choices = 1;
                selected_target = target;
            } else if (weight == maximum_weight) {
                ++choices;
                if (rng() % static_cast<std::uint64_t>(choices) == 0) {
                    selected_target = target;
                }
            }
        }
        return selected_target;
    }

    [[nodiscard]] Candidate best_targeted_swap(
        int target,
        const std::vector<std::uint64_t>& tabu_until,
        std::uint64_t iteration,
        int global_best_uncovered,
        std::mt19937_64& rng
    ) const {
        std::array<std::uint64_t, kCodeSize> loss_weight{};
        std::array<int, kCodeSize> loss_count{};
        std::array<int, kCodeSize> remove_singleton_delta{};

        for (int position = 1; position < kCodeSize; ++position) {
            const int word = code_[static_cast<std::size_t>(position)];
            for (const int covered :
                 balls_[static_cast<std::size_t>(word)]) {
                const int count = std::popcount(
                    coverage_mask_[static_cast<std::size_t>(covered)]
                );
                if (count == 1) {
                    loss_weight[static_cast<std::size_t>(position)] +=
                        weights_[static_cast<std::size_t>(covered)];
                    ++loss_count[static_cast<std::size_t>(position)];
                    --remove_singleton_delta[
                        static_cast<std::size_t>(position)
                    ];
                } else if (count == 2) {
                    ++remove_singleton_delta[
                        static_cast<std::size_t>(position)
                    ];
                }
            }
        }

        Candidate best;
        for (const int add_word :
             balls_[static_cast<std::size_t>(target)]) {
            if (selected(add_word)) {
                continue;
            }

            std::uint64_t gain_weight = 0;
            int gain_count = 0;
            int add_singleton_delta = 0;
            std::array<std::uint64_t, kCodeSize> recovery_weight{};
            std::array<int, kCodeSize> recovery_count{};
            std::array<int, kCodeSize> interaction_correction{};

            for (const int covered :
                 balls_[static_cast<std::size_t>(add_word)]) {
                const std::uint16_t mask =
                    coverage_mask_[static_cast<std::size_t>(covered)];
                const int count = std::popcount(mask);
                if (count == 0) {
                    gain_weight +=
                        weights_[static_cast<std::size_t>(covered)];
                    ++gain_count;
                    ++add_singleton_delta;
                } else if (count == 1) {
                    const int owner = std::countr_zero(mask);
                    recovery_weight[static_cast<std::size_t>(owner)] +=
                        weights_[static_cast<std::size_t>(covered)];
                    ++recovery_count[static_cast<std::size_t>(owner)];
                    interaction_correction[
                        static_cast<std::size_t>(owner)
                    ] += 2;
                    --add_singleton_delta;
                } else if (count == 2) {
                    std::uint16_t owners = mask;
                    while (owners != 0) {
                        const int owner = std::countr_zero(owners);
                        --interaction_correction[
                            static_cast<std::size_t>(owner)
                        ];
                        owners &= static_cast<std::uint16_t>(owners - 1);
                    }
                }
            }

            for (int position = 1; position < kCodeSize; ++position) {
                const std::int64_t weighted =
                    static_cast<std::int64_t>(
                        metrics_.weighted_uncovered
                    ) +
                    static_cast<std::int64_t>(
                        loss_weight[static_cast<std::size_t>(position)]
                    ) -
                    static_cast<std::int64_t>(
                        recovery_weight[static_cast<std::size_t>(position)]
                    ) -
                    static_cast<std::int64_t>(gain_weight);
                if (weighted < 0) {
                    throw std::logic_error(
                        "candidate weighted score became negative"
                    );
                }
                const int uncovered =
                    metrics_.uncovered +
                    loss_count[static_cast<std::size_t>(position)] -
                    recovery_count[static_cast<std::size_t>(position)] -
                    gain_count;
                const int singletons =
                    metrics_.singletons +
                    remove_singleton_delta[
                        static_cast<std::size_t>(position)
                    ] +
                    add_singleton_delta +
                    interaction_correction[
                        static_cast<std::size_t>(position)
                    ];

                const bool tabu =
                    tabu_until[static_cast<std::size_t>(add_word)] >
                    iteration;
                if (tabu && uncovered >= global_best_uncovered) {
                    continue;
                }

                Candidate candidate{
                    position,
                    add_word,
                    static_cast<std::uint64_t>(weighted),
                    uncovered,
                    singletons,
                    rng(),
                };
                if (std::tie(
                        candidate.weighted_uncovered,
                        candidate.uncovered,
                        candidate.singletons,
                        candidate.tie_break
                    ) <
                    std::tie(
                        best.weighted_uncovered,
                        best.uncovered,
                        best.singletons,
                        best.tie_break
                    )) {
                    best = candidate;
                }
            }
        }
        return best;
    }

    int apply_swap(int remove_position, int add_word) {
        if (remove_position <= 0 || remove_position >= kCodeSize) {
            throw std::invalid_argument("cannot remove the anchored position");
        }
        if (selected(add_word)) {
            throw std::invalid_argument("replacement word is already selected");
        }

        const int removed =
            code_[static_cast<std::size_t>(remove_position)];
        const std::uint16_t bit =
            static_cast<std::uint16_t>(1U << remove_position);
        for (const int target :
             balls_[static_cast<std::size_t>(removed)]) {
            const int before = std::popcount(
                coverage_mask_[static_cast<std::size_t>(target)]
            );
            coverage_mask_[static_cast<std::size_t>(target)] &=
                static_cast<std::uint16_t>(~bit);
            update_metrics_for_count_change(target, before, before - 1);
        }

        position_[static_cast<std::size_t>(removed)] = -1;
        position_[static_cast<std::size_t>(add_word)] = remove_position;
        code_[static_cast<std::size_t>(remove_position)] = add_word;

        for (const int target :
             balls_[static_cast<std::size_t>(add_word)]) {
            const int before = std::popcount(
                coverage_mask_[static_cast<std::size_t>(target)]
            );
            coverage_mask_[static_cast<std::size_t>(target)] |= bit;
            update_metrics_for_count_change(target, before, before + 1);
        }
        return removed;
    }

    void increase_uncovered_weights(std::uint32_t increment) {
        for (int target = 0; target < kAmbient; ++target) {
            if (coverage_mask_[static_cast<std::size_t>(target)] != 0) {
                continue;
            }
            auto& weight = weights_[static_cast<std::size_t>(target)];
            if (weight >
                std::numeric_limits<std::uint32_t>::max() - increment) {
                throw std::overflow_error("breakout weight overflow");
            }
            weight += increment;
            metrics_.weighted_uncovered += increment;
        }
    }

    [[nodiscard]] std::vector<int> uncovered_words() const {
        std::vector<int> words;
        for (int word = 0; word < kAmbient; ++word) {
            if (coverage_mask_[static_cast<std::size_t>(word)] == 0) {
                words.push_back(word);
            }
        }
        return words;
    }

    void assert_consistent() const {
        std::array<std::uint16_t, kAmbient> expected{};
        for (int position = 0; position < kCodeSize; ++position) {
            const int word = code_[static_cast<std::size_t>(position)];
            for (const int target :
                 balls_[static_cast<std::size_t>(word)]) {
                expected[static_cast<std::size_t>(target)] |=
                    static_cast<std::uint16_t>(1U << position);
            }
        }
        if (expected != coverage_mask_) {
            throw std::logic_error("incremental coverage masks are incorrect");
        }

        Metrics expected_metrics;
        for (int target = 0; target < kAmbient; ++target) {
            const int count = std::popcount(
                expected[static_cast<std::size_t>(target)]
            );
            if (count == 0) {
                ++expected_metrics.uncovered;
                expected_metrics.weighted_uncovered +=
                    weights_[static_cast<std::size_t>(target)];
            } else if (count == 1) {
                ++expected_metrics.singletons;
            }
        }
        if (std::tie(
                expected_metrics.uncovered,
                expected_metrics.singletons,
                expected_metrics.weighted_uncovered
            ) !=
            std::tie(
                metrics_.uncovered,
                metrics_.singletons,
                metrics_.weighted_uncovered
            )) {
            throw std::logic_error("incremental metrics are incorrect");
        }
    }

  private:
    Code code_;
    const std::vector<Ball>& balls_;
    std::vector<std::uint32_t>& weights_;
    std::array<int, kAmbient> position_{};
    std::array<std::uint16_t, kAmbient> coverage_mask_{};
    Metrics metrics_;

    void rebuild_metrics() {
        metrics_ = Metrics{};
        for (int target = 0; target < kAmbient; ++target) {
            const int count = std::popcount(
                coverage_mask_[static_cast<std::size_t>(target)]
            );
            if (count == 0) {
                ++metrics_.uncovered;
                metrics_.weighted_uncovered +=
                    weights_[static_cast<std::size_t>(target)];
            } else if (count == 1) {
                ++metrics_.singletons;
            }
        }
    }

    void update_metrics_for_count_change(
        int target,
        int before,
        int after
    ) {
        const std::uint64_t weight =
            weights_[static_cast<std::size_t>(target)];
        if (before == 0) {
            --metrics_.uncovered;
            metrics_.weighted_uncovered -= weight;
        } else if (before == 1) {
            --metrics_.singletons;
        }
        if (after == 0) {
            ++metrics_.uncovered;
            metrics_.weighted_uncovered += weight;
        } else if (after == 1) {
            ++metrics_.singletons;
        }
    }
};

Code baseline_start(std::mt19937_64& rng) {
    const int omitted = 1 + static_cast<int>(rng() % 15U);
    Code code{};
    int output = 0;
    for (int index = 0; index < 16; ++index) {
        if (index == omitted) {
            continue;
        }
        code[static_cast<std::size_t>(output++)] =
            kBaseline[static_cast<std::size_t>(index)];
    }
    return code;
}

Code greedy_start(
    std::mt19937_64& rng,
    const std::vector<Ball>& balls
) {
    Code code{};
    code.fill(-1);
    code[0] = 0;
    std::array<bool, kAmbient> selected{};
    std::array<int, kAmbient> coverage{};
    selected[0] = true;
    for (const int target : balls[0]) {
        ++coverage[static_cast<std::size_t>(target)];
    }

    for (int position = 1; position < kCodeSize; ++position) {
        int best_word = -1;
        int best_gain = -1;
        std::uint64_t best_tie = 0;
        for (int word = 1; word < kAmbient; ++word) {
            if (selected[static_cast<std::size_t>(word)]) {
                continue;
            }
            int gain = 0;
            for (const int target : balls[static_cast<std::size_t>(word)]) {
                gain += coverage[static_cast<std::size_t>(target)] == 0;
            }
            const std::uint64_t tie = rng();
            if (std::tie(gain, tie) > std::tie(best_gain, best_tie)) {
                best_word = word;
                best_gain = gain;
                best_tie = tie;
            }
        }
        code[static_cast<std::size_t>(position)] = best_word;
        selected[static_cast<std::size_t>(best_word)] = true;
        for (const int target :
             balls[static_cast<std::size_t>(best_word)]) {
            ++coverage[static_cast<std::size_t>(target)];
        }
    }
    return code;
}

bool better_raw(const Metrics& left, const Metrics& right) {
    return std::tie(left.uncovered, left.singletons) <
           std::tie(right.uncovered, right.singletons);
}

std::string word_text(int word) {
    std::string result(static_cast<std::size_t>(kLength), '0');
    for (int bit = 0; bit < kLength; ++bit) {
        if ((word >> bit & 1) != 0) {
            result[static_cast<std::size_t>(kLength - bit - 1)] = '1';
        }
    }
    return result;
}

void write_code(const std::string& path, Code code) {
    if (path.empty()) {
        return;
    }
    std::sort(code.begin(), code.end());
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("failed to open code output");
    }
    for (const int word : code) {
        output << word_text(word) << '\n';
    }
}

void write_summary(
    const std::string& path,
    const Options& options,
    std::uint64_t executed,
    std::uint64_t restarts,
    const Metrics& best,
    const Code& best_code,
    const std::vector<int>& uncovered,
    double elapsed_seconds
) {
    if (path.empty()) {
        return;
    }
    std::ofstream output(path);
    if (!output) {
        throw std::runtime_error("failed to open summary output");
    }
    output << "{\n"
           << "  \"algorithm\": \"targeted-breakout-one-swap\",\n"
           << "  \"length\": " << kLength << ",\n"
           << "  \"radius\": " << kRadius << ",\n"
           << "  \"size\": " << kCodeSize << ",\n"
           << "  \"anchor_zero\": true,\n"
           << "  \"seed\": " << options.seed << ",\n"
           << "  \"iterations_requested\": " << options.iterations << ",\n"
           << "  \"iterations_executed\": " << executed << ",\n"
           << "  \"restarts\": " << restarts << ",\n"
           << "  \"elapsed_seconds\": " << elapsed_seconds << ",\n"
           << "  \"best_uncovered\": " << best.uncovered << ",\n"
           << "  \"best_singletons\": " << best.singletons << ",\n"
           << "  \"found_cover\": "
           << (best.uncovered == 0 ? "true" : "false") << ",\n"
           << "  \"proof_trace_available\": false,\n"
           << "  \"codewords\": [";
    for (int index = 0; index < kCodeSize; ++index) {
        if (index != 0) {
            output << ", ";
        }
        output << best_code[static_cast<std::size_t>(index)];
    }
    output << "],\n  \"uncovered_words\": [";
    for (std::size_t index = 0; index < uncovered.size(); ++index) {
        if (index != 0) {
            output << ", ";
        }
        output << uncovered[index];
    }
    output << "]\n}\n";
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; ++index) {
        const std::string argument = argv[index];
        auto value = [&](const char* name) -> std::string {
            if (++index >= argc) {
                throw std::invalid_argument(
                    std::string("missing value for ") + name
                );
            }
            return argv[index];
        };
        if (argument == "--iterations") {
            options.iterations = std::stoull(value("--iterations"));
        } else if (argument == "--restart-iterations") {
            options.restart_iterations =
                std::stoull(value("--restart-iterations"));
        } else if (argument == "--breakout-stagnation") {
            options.breakout_stagnation =
                std::stoull(value("--breakout-stagnation"));
        } else if (argument == "--seed") {
            options.seed = std::stoull(value("--seed"));
        } else if (argument == "--best-code") {
            options.best_code_path = value("--best-code");
        } else if (argument == "--summary") {
            options.summary_path = value("--summary");
        } else if (argument == "--self-test") {
            options.self_test = true;
        } else if (argument == "--quiet") {
            options.quiet = true;
        } else {
            throw std::invalid_argument("unknown argument: " + argument);
        }
    }
    if (options.iterations == 0 ||
        options.restart_iterations == 0 ||
        options.breakout_stagnation == 0) {
        throw std::invalid_argument("iteration controls must be positive");
    }
    return options;
}

void run_self_test(const std::vector<Ball>& balls) {
    for (int center = 0; center < kAmbient; ++center) {
        for (const int target : balls[static_cast<std::size_t>(center)]) {
            if (std::popcount(
                    static_cast<unsigned int>(center ^ target)
                ) > kRadius) {
                throw std::logic_error("ball contains a distant word");
            }
        }
    }

    std::mt19937_64 rng(20260902);
    std::vector<std::uint32_t> weights(
        static_cast<std::size_t>(kAmbient),
        1
    );
    State state(baseline_start(rng), balls, weights);
    state.assert_consistent();
    for (int iteration = 0; iteration < 1000; ++iteration) {
        const int position = 1 + static_cast<int>(rng() % 14U);
        int add_word = static_cast<int>(rng() % kAmbient);
        while (state.selected(add_word)) {
            add_word = static_cast<int>(rng() % kAmbient);
        }
        state.apply_swap(position, add_word);
        if (iteration % 37 == 0) {
            state.increase_uncovered_weights(1);
        }
        state.assert_consistent();
    }
    std::cout << "self-test passed\n";
}

int run(const Options& options, const std::vector<Ball>& balls) {
    std::mt19937_64 rng(options.seed);
    Metrics global_best{
        std::numeric_limits<int>::max(),
        std::numeric_limits<int>::max(),
        0,
    };
    Code global_best_code{};
    std::vector<int> global_best_uncovered;
    std::uint64_t executed = 0;
    std::uint64_t restarts = 0;
    const auto started = std::chrono::steady_clock::now();

    while (executed < options.iterations && global_best.uncovered != 0) {
        std::vector<std::uint32_t> weights(
            static_cast<std::size_t>(kAmbient),
            1
        );
        Code start = restarts % 4 == 3
            ? greedy_start(rng, balls)
            : baseline_start(rng);
        State state(start, balls, weights);
        Metrics local_best = state.metrics();
        std::uint64_t local_stagnation = 0;
        std::vector<std::uint64_t> tabu_until(
            static_cast<std::size_t>(kAmbient),
            0
        );

        auto record = [&]() {
            if (!better_raw(state.metrics(), global_best)) {
                return;
            }
            global_best = state.metrics();
            global_best_code = state.code();
            global_best_uncovered = state.uncovered_words();
            write_code(options.best_code_path, global_best_code);
            if (!options.quiet) {
                std::cerr
                    << "iteration=" << executed
                    << " restart=" << restarts
                    << " uncovered=" << global_best.uncovered
                    << " singletons=" << global_best.singletons
                    << '\n';
            }
        };
        record();

        const std::uint64_t restart_limit = std::min(
            options.restart_iterations,
            options.iterations - executed
        );
        for (std::uint64_t local_iteration = 1;
             local_iteration <= restart_limit &&
             global_best.uncovered != 0;
             ++local_iteration) {
            ++executed;
            const int target = state.choose_uncovered_target(rng);
            if (target < 0) {
                record();
                break;
            }
            const Candidate candidate = state.best_targeted_swap(
                target,
                tabu_until,
                executed,
                global_best.uncovered,
                rng
            );
            if (candidate.remove_position < 0) {
                throw std::logic_error("no admissible targeted swap exists");
            }
            const int removed = state.apply_swap(
                candidate.remove_position,
                candidate.add_word
            );
            tabu_until[static_cast<std::size_t>(removed)] =
                executed + 5U + rng() % 11U;

            if (better_raw(state.metrics(), local_best)) {
                local_best = state.metrics();
                local_stagnation = 0;
            } else {
                ++local_stagnation;
            }
            record();

            if (local_stagnation > 0 &&
                local_stagnation % options.breakout_stagnation == 0) {
                state.increase_uncovered_weights(1);
            }
        }
        ++restarts;
    }

    const double elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started
    ).count();
    write_code(options.best_code_path, global_best_code);
    write_summary(
        options.summary_path,
        options,
        executed,
        restarts,
        global_best,
        global_best_code,
        global_best_uncovered,
        elapsed
    );
    std::cout
        << "best_uncovered=" << global_best.uncovered
        << " best_singletons=" << global_best.singletons
        << " iterations=" << executed
        << " restarts=" << restarts
        << " elapsed_seconds=" << elapsed
        << '\n';
    return global_best.uncovered == 0 ? 0 : 2;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Options options = parse_options(argc, argv);
        const std::vector<Ball> balls = build_balls();
        if (options.self_test) {
            run_self_test(balls);
            return 0;
        }
        return run(options, balls);
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 1;
    }
}
