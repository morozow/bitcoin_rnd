/**
 * @file test_error.cpp
 * @brief Tests for error handling
 */

#include <gtest/gtest.h>
#include <stdiobus/error.hpp>

using namespace stdiobus;

TEST(ErrorCode, Values) {
    EXPECT_EQ(static_cast<int>(ErrorCode::Ok), 0);
    EXPECT_EQ(static_cast<int>(ErrorCode::Error), -1);
    EXPECT_EQ(static_cast<int>(ErrorCode::Again), -2);
    EXPECT_EQ(static_cast<int>(ErrorCode::Eof), -3);
    EXPECT_EQ(static_cast<int>(ErrorCode::Full), -4);
    EXPECT_EQ(static_cast<int>(ErrorCode::NotFound), -5);
    EXPECT_EQ(static_cast<int>(ErrorCode::Invalid), -6);
    EXPECT_EQ(static_cast<int>(ErrorCode::Config), -10);
    EXPECT_EQ(static_cast<int>(ErrorCode::Worker), -11);
    EXPECT_EQ(static_cast<int>(ErrorCode::Routing), -12);
    EXPECT_EQ(static_cast<int>(ErrorCode::Buffer), -13);
    EXPECT_EQ(static_cast<int>(ErrorCode::State), -15);
    EXPECT_EQ(static_cast<int>(ErrorCode::Timeout), -20);
    EXPECT_EQ(static_cast<int>(ErrorCode::PolicyDenied), -21);
}

TEST(ErrorCode, Names) {
    EXPECT_EQ(error_code_name(ErrorCode::Ok), "Ok");
    EXPECT_EQ(error_code_name(ErrorCode::Error), "Error");
    EXPECT_EQ(error_code_name(ErrorCode::Timeout), "Timeout");
    EXPECT_EQ(error_code_name(ErrorCode::PolicyDenied), "PolicyDenied");
}

TEST(ErrorCode, Retryable) {
    EXPECT_TRUE(is_retryable(ErrorCode::Again));
    EXPECT_TRUE(is_retryable(ErrorCode::Full));
    EXPECT_TRUE(is_retryable(ErrorCode::Timeout));
    
    EXPECT_FALSE(is_retryable(ErrorCode::Ok));
    EXPECT_FALSE(is_retryable(ErrorCode::Error));
    EXPECT_FALSE(is_retryable(ErrorCode::Invalid));
    EXPECT_FALSE(is_retryable(ErrorCode::PolicyDenied));
}

TEST(Error, DefaultConstruction) {
    Error err;
    EXPECT_FALSE(err);  // No error
    EXPECT_EQ(err.code(), ErrorCode::Ok);
}

TEST(Error, FromCode) {
    Error err(ErrorCode::Timeout);
    EXPECT_TRUE(err);  // Has error
    EXPECT_EQ(err.code(), ErrorCode::Timeout);
    EXPECT_EQ(err.message(), "Timeout");
}

TEST(Error, WithMessage) {
    Error err(ErrorCode::Config, "Invalid JSON");
    EXPECT_TRUE(err);
    EXPECT_EQ(err.code(), ErrorCode::Config);
    EXPECT_EQ(err.message(), "Invalid JSON");
}

TEST(Error, Ok) {
    auto err = Error::ok();
    EXPECT_FALSE(err);
    EXPECT_EQ(err.code(), ErrorCode::Ok);
}

TEST(Error, FromC) {
    auto err = Error::from_c(-10);
    EXPECT_TRUE(err);
    EXPECT_EQ(err.code(), ErrorCode::Config);
    
    auto ok = Error::from_c(0);
    EXPECT_FALSE(ok);
}

TEST(Error, IsRetryable) {
    EXPECT_TRUE(Error(ErrorCode::Again).is_retryable());
    EXPECT_TRUE(Error(ErrorCode::Timeout).is_retryable());
    EXPECT_FALSE(Error(ErrorCode::Invalid).is_retryable());
}

TEST(Error, BoolConversion) {
    Error ok;
    Error err(ErrorCode::Error);
    
    if (ok) {
        FAIL() << "Ok should be false";
    }
    
    if (!err) {
        FAIL() << "Error should be true";
    }
}

#ifdef STDIOBUS_CPP_EXCEPTIONS
TEST(Exception, Throw) {
    Error err(ErrorCode::Config, "Test error");
    EXPECT_THROW(throw_if_error(err), Exception);
}

TEST(Exception, NoThrowOnOk) {
    Error ok;
    EXPECT_NO_THROW(throw_if_error(ok));
}

TEST(Exception, What) {
    try {
        throw Exception(Error(ErrorCode::Timeout, "Request timed out"));
    } catch (const Exception& e) {
        EXPECT_STREQ(e.what(), "Request timed out");
        EXPECT_EQ(e.code(), ErrorCode::Timeout);
    }
}
#endif
